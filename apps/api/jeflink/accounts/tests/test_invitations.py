"""Tâche 12 : invitations à un rôle pro (S19), SMS générique, limites, acceptation."""

import uuid
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from jeflink.accounts import services, tasks
from jeflink.accounts.models import NoticeSms, Role, RoleGrant, RoleInvitation, User
from jeflink.accounts.otp_limits import reserve_sms
from jeflink.accounts.services import (
    accept_invitation,
    decline_invitation,
    grant_role,
    invite_to_role,
    register_invitation_handler,
)
from jeflink.accounts.sessions import create_session
from jeflink.common.errors import DomainError
from jeflink.notifications.sms import SmsPermanentError, SmsResult, SmsTransientError
from jeflink.notifications.sms.fake import FakeSmsGateway
from jeflink.trust.models import AuditEvent

from .otp_helpers import request_code, verify

pytestmark = pytest.mark.django_db

CHEIKH = "+221781234567"
TEAM = uuid.UUID("7c9e6679-7425-40de-944b-e07fc1f90ae7")


@pytest.fixture
def fatou(complete_user_factory):
    owner = complete_user_factory(display_name="Fatou Nettoyage")
    grant_role(user=owner, role=Role.OWNER, reason_code="test")
    return owner


@pytest.fixture
def invite(fatou, django_capture_on_commit_callbacks):
    def _invite(phone=CHEIKH, *, role=Role.TECHNICIAN, by=None, context_ref=TEAM, hint=""):
        with django_capture_on_commit_callbacks(execute=True):
            return invite_to_role(
                phone=phone,
                role=role,
                invited_by=by or fatou,
                context_ref=context_ref,
                display_name_hint=hint,
            )

    return _invite


@pytest.fixture
def handlers(monkeypatch):
    """Registre des gestionnaires isolé : providers n'existe pas encore."""
    registry: dict = {}
    monkeypatch.setattr(services, "_INVITATION_HANDLERS", registry)
    return registry


def bearer(api_client, user, **kwargs):
    pair = create_session(user=user, app="pro", platform="android", **kwargs)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {pair.access}")
    return api_client


class ScriptedGateway:
    name = "scripted"

    def __init__(self, *errors):
        self.errors = list(errors)
        self.bodies = []

    def send(self, *, to, body, idempotency_key, sender_id):
        self.bodies.append(body)
        if self.errors:
            raise self.errors.pop(0)
        return SmsResult(gateway=self.name, provider_message_id="m1", segments=1, status="sent")


# --- Invitation --------------------------------------------------------------------------------


def test_invitation_en_attente_sans_compte_ni_role(invite, fatou):
    users_before = User.objects.count()
    invitation = invite(" 78 123 45 67 ", hint="Cheikh")
    assert invitation.status == RoleInvitation.Status.PENDING
    assert invitation.phone == CHEIKH
    assert invitation.display_name_hint == "Cheikh"
    assert invitation.expires_at - timezone.now() > timedelta(days=6, hours=23)
    # S19 : aucun User ni RoleGrant avant la connexion et l'acceptation.
    assert User.objects.count() == users_before
    assert not RoleGrant.objects.exclude(user=fatou).exists()


def test_sms_generique_sans_nom_du_pro(invite):
    invite()
    [sms] = FakeSmsGateway.outbox
    assert sms.to == CHEIKH
    assert "Fatou" not in sms.body and "Nettoyage" not in sms.body
    assert sms.body.startswith("Jeflink Pro : une équipe vous invite")
    notice = NoticeSms.objects.get()
    assert (notice.kind, notice.status, notice.phone) == ("invitation", "sent", "")
    assert notice.phone_hmac


def test_reponse_identique_compte_existant_ou_non(invite, user_factory):
    """Critère S19 : rien, côté pro, ne dépend de l'existence d'un compte sur le numéro."""
    user_factory(phone="+221771111111")
    avec_compte = invite("+221771111111")
    sans_compte = invite("+221772222222")
    champs = ["status", "role", "display_name_hint", "context_ref"]
    assert [getattr(avec_compte, c) for c in champs] == [getattr(sans_compte, c) for c in champs]
    assert len(FakeSmsGateway.outbox) == 2


def test_reinviter_pendant_la_validite_ne_renvoie_pas_de_sms(invite):
    first = invite()
    assert invite().pk == first.pk
    assert len(FakeSmsGateway.outbox) == 1


def test_invitation_expiree_renouvelee(invite):
    old = invite()
    RoleInvitation.objects.filter(pk=old.pk).update(expires_at=timezone.now() - timedelta(1))
    new = invite()
    old.refresh_from_db()
    assert new.pk != old.pk
    assert (old.status, old.phone) == ("expired", "")
    assert len(FakeSmsGateway.outbox) == 2


def test_quota_de_20_invitations_par_jour_et_par_pro(invite, settings):
    for n in range(settings.INVITATIONS_PER_INVITER_DAILY):
        invite(f"+22176000{n:04d}")
    with pytest.raises(DomainError) as exc:
        invite("+221769999999")
    assert exc.value.code == "invitation_rate_limited"
    assert exc.value.status_code == 429
    assert 0 < exc.value.extra["retry_after"] <= 86400


def test_deux_sms_d_invitation_par_numero_et_par_jour(invite, complete_user_factory):
    """Un pro ne peut pas épuiser le budget SMS de connexion d'un numéro avec des invitations."""
    for _ in range(3):
        invite(context_ref=uuid.uuid4(), by=complete_user_factory())
    assert RoleInvitation.objects.filter(status="pending").count() == 3
    assert len(FakeSmsGateway.outbox) == 2


def test_budget_sms_du_numero_epuise_invitation_creee_sans_sms(invite):
    for _ in range(5):
        reserve_sms(phone=CHEIKH, region="SN", new_challenge=False)
    invitation = invite()
    assert invitation.status == "pending"
    assert FakeSmsGateway.outbox == []
    assert not NoticeSms.objects.exists()


def test_redis_coupe_invitation_creee_sans_sms(invite, redis_down):
    assert invite().status == "pending"
    assert FakeSmsGateway.outbox == []


def test_les_sms_d_invitation_comptent_dans_le_budget_du_numero(invite, complete_user_factory):
    invite(context_ref=uuid.uuid4(), by=complete_user_factory())
    invite(context_ref=uuid.uuid4(), by=complete_user_factory())
    for _ in range(3):
        reserve_sms(phone=CHEIKH, region="SN", new_challenge=False)
    with pytest.raises(DomainError) as exc:
        reserve_sms(phone=CHEIKH, region="SN", new_challenge=False)
    assert exc.value.code == "otp_rate_limited"


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"role": Role.OPS}, "role_unknown"),
        ({"phone": "+33612345678"}, "phone_region_not_supported"),
        ({"phone": "12"}, "phone_invalid"),
        ({"hint": "Support Jeflink"}, "display_name_reserved"),
    ],
)
def test_invitation_refusee(invite, kwargs, code):
    with pytest.raises(DomainError) as exc:
        invite(**kwargs)
    assert exc.value.code == code
    assert not RoleInvitation.objects.exists()
    assert FakeSmsGateway.outbox == []


def test_pas_d_invitation_a_soi_meme(invite, fatou):
    with pytest.raises(DomainError) as exc:
        invite(fatou.phone)
    assert exc.value.code == "invitation_self"


def test_pro_desactive_ne_peut_pas_inviter(invite, fatou):
    User.objects.filter(pk=fatou.pk).update(is_active=False, deactivation_reason="fraud")
    with pytest.raises(DomainError) as exc:
        invite()
    assert exc.value.code == "account_disabled"


# --- Envoi du SMS d'information ------------------------------------------------------------------


def test_envoi_echoue_definitivement(invite, monkeypatch):
    monkeypatch.setattr(tasks, "get_sms_gateway", lambda: ScriptedGateway(SmsPermanentError("E1")))
    invite()
    notice = NoticeSms.objects.get()
    assert (notice.status, notice.error_code, notice.phone) == ("failed", "E1", "")


def test_erreur_transitoire_nouvel_essai(invite, monkeypatch):
    gateway = ScriptedGateway(SmsTransientError("timeout"))
    monkeypatch.setattr(tasks, "get_sms_gateway", lambda: gateway)
    invite()
    assert len(gateway.bodies) == 2
    assert NoticeSms.objects.get().status == "sent"


def test_relivraison_en_plein_envoi_pas_de_double_sms(invite, monkeypatch):
    monkeypatch.setattr(tasks.send_notice_sms, "delay", lambda *a, **kw: None)
    invite()
    notice = NoticeSms.objects.get()
    NoticeSms.objects.filter(pk=notice.pk).update(status="sending")
    tasks.send_notice_sms(str(notice.public_id))
    notice.refresh_from_db()
    assert (notice.status, notice.phone) == ("unknown", "")
    assert FakeSmsGateway.outbox == []
    # Déjà clos : une nouvelle livraison ne fait rien.
    tasks.send_notice_sms(str(notice.public_id))
    assert FakeSmsGateway.outbox == []


# --- Acceptation et refus ------------------------------------------------------------------------


def test_acceptation(invite, fatou, complete_user_factory, handlers):
    received = []
    register_invitation_handler(Role.TECHNICIAN, received.append)
    cheikh = complete_user_factory(phone=CHEIKH)
    invitation = invite()
    grant = accept_invitation(user=cheikh, invitation_public_id=invitation.public_id)
    assert (grant.user, grant.role, grant.granted_by) == (cheikh, "technician", fatou)
    invitation.refresh_from_db()
    assert (invitation.status, invitation.phone, invitation.accepted_by) == (
        "accepted",
        "",
        cheikh,
    )
    [accepted] = received
    assert (accepted.user, accepted.context_ref, accepted.invited_by) == (cheikh, TEAM, fatou)
    event = AuditEvent.objects.get(action="accounts.invitation.accepted")
    assert (event.actor, event.actor_kind) == (cheikh, "user")
    assert event.metadata == {
        "role": "technician",
        "invitation": str(invitation.public_id),
        "invited_by": str(fatou.public_id),
    }
    granted = AuditEvent.objects.filter(
        action="accounts.role.granted", target_public_id=cheikh.public_id
    )
    assert granted.get().actor_kind == "user"


def test_invite_sans_nom_complete_par_le_nom_propose(invite, user_factory):
    cheikh = user_factory(phone=CHEIKH)
    invitation = invite(hint="Cheikh")
    accept_invitation(user=cheikh, invitation_public_id=invitation.public_id)
    cheikh.refresh_from_db()
    assert (cheikh.display_name, cheikh.profile_status) == ("Cheikh", "complete")


def test_invite_sans_nom_ni_nom_propose(invite, user_factory):
    cheikh = user_factory(phone=CHEIKH)
    invitation = invite()
    with pytest.raises(DomainError) as exc:
        accept_invitation(user=cheikh, invitation_public_id=invitation.public_id)
    assert exc.value.code == "profile_incomplete"
    assert not cheikh.role_grants.exists()


def test_le_nom_propose_n_ecrase_pas_un_profil_complet(invite, complete_user_factory):
    cheikh = complete_user_factory(phone=CHEIKH, display_name="Cheikh Ndiaye")
    accept_invitation(user=cheikh, invitation_public_id=invite(hint="Cheikh").public_id)
    cheikh.refresh_from_db()
    assert cheikh.display_name == "Cheikh Ndiaye"


@pytest.mark.parametrize("case", ["autre_numero", "expiree", "declinee", "pro_desactive"])
def test_invitation_introuvable(invite, fatou, complete_user_factory, case):
    cheikh = complete_user_factory(phone=CHEIKH)
    invitation = invite()
    if case == "autre_numero":
        cheikh = complete_user_factory(phone="+221770000001")
    elif case == "expiree":
        RoleInvitation.objects.filter(pk=invitation.pk).update(expires_at=timezone.now())
    elif case == "declinee":
        decline_invitation(user=cheikh, invitation_public_id=invitation.public_id)
    else:
        User.objects.filter(pk=fatou.pk).update(is_active=False, deactivation_reason="fraud")
    with pytest.raises(DomainError) as exc:
        accept_invitation(user=cheikh, invitation_public_id=invitation.public_id)
    assert (exc.value.code, exc.value.status_code) == ("not_found", 404)
    assert not cheikh.role_grants.exists()


def test_refus_du_gestionnaire_annule_tout(invite, complete_user_factory, handlers):
    def refuse(accepted):
        raise DomainError("team_full", status=409)

    register_invitation_handler(Role.TECHNICIAN, refuse)
    cheikh = complete_user_factory(phone=CHEIKH)
    invitation = invite()
    with pytest.raises(DomainError):
        accept_invitation(user=cheikh, invitation_public_id=invitation.public_id)
    invitation.refresh_from_db()
    assert invitation.status == "pending"
    assert not cheikh.role_grants.exists()
    assert not AuditEvent.objects.filter(action="accounts.invitation.accepted").exists()


def test_compte_de_revue_ne_recoit_pas_de_role(invite, complete_user_factory):
    cheikh = complete_user_factory(phone=CHEIKH, is_review_account=True)
    invitation = invite()
    with pytest.raises(DomainError) as exc:
        accept_invitation(user=cheikh, invitation_public_id=invitation.public_id)
    assert exc.value.code == "role_not_allowed"
    invitation.refresh_from_db()
    assert invitation.status == "pending"


def test_refus(invite, user_factory):
    cheikh = user_factory(phone=CHEIKH)
    invitation = invite()
    decline_invitation(user=cheikh, invitation_public_id=invitation.public_id)
    invitation.refresh_from_db()
    assert (invitation.status, invitation.phone) == ("declined", "")
    assert invitation.declined_at is not None
    assert not cheikh.role_grants.exists()


def test_registre_des_gestionnaires(handlers):
    def handler(accepted):
        return None

    register_invitation_handler(Role.OWNER, handler)
    register_invitation_handler(Role.OWNER, handler)  # idempotent
    with pytest.raises(ValueError):
        register_invitation_handler(Role.OWNER, lambda accepted: None)
    with pytest.raises(ValueError):
        register_invitation_handler(Role.OPS, handler)


# --- API -----------------------------------------------------------------------------------------


def test_liste_de_mes_invitations(api_client, invite, complete_user_factory, fatou):
    cheikh = complete_user_factory(phone=CHEIKH)
    invitation = invite(hint="Cheikh")
    invite("+221770000001")  # invitation d'un autre numéro : jamais listée
    response = bearer(api_client, cheikh).get(reverse("me-invitations"))
    assert response.status_code == 200
    assert response.json()["results"] == [
        {
            "public_id": str(invitation.public_id),
            "role": "technician",
            "invited_by_name": "Fatou Nettoyage",
            "display_name_hint": "Cheikh",
            "context_ref": str(TEAM),
            "expires_at": response.json()["results"][0]["expires_at"],
        }
    ]


def test_accepter_et_refuser_par_l_api(api_client, invite, complete_user_factory):
    cheikh = complete_user_factory(phone=CHEIKH)
    client = bearer(api_client, cheikh)
    first = invite()
    second = invite(role=Role.OWNER)
    url = reverse("me-invitation-accept", args=[first.public_id])
    assert client.post(url).status_code == 204
    assert client.post(url).status_code == 404  # déjà acceptée
    response = client.post(reverse("me-invitation-decline", args=[second.public_id]))
    assert response.status_code == 204
    assert set(cheikh.role_grants.values_list("role", flat=True)) == {"technician"}


def test_invitation_d_un_autre_404(api_client, invite, complete_user_factory):
    invitation = invite()
    client = bearer(api_client, complete_user_factory(phone="+221770000001"))
    response = client.post(reverse("me-invitation-accept", args=[invitation.public_id]))
    assert response.status_code == 404
    assert response.json() == {"code": "not_found"}


def test_accepter_sans_profil_complet_403(api_client, invite, user_factory):
    invitation = invite()
    client = bearer(api_client, user_factory(phone=CHEIKH))
    response = client.post(reverse("me-invitation-accept", args=[invitation.public_id]))
    assert response.status_code == 403
    assert response.json() == {"code": "profile_incomplete"}


def test_session_restreinte_ne_voit_pas_les_invitations(api_client, invite, complete_user_factory):
    invite()
    client = bearer(api_client, complete_user_factory(phone=CHEIKH), restricted=True)
    response = client.get(reverse("me-invitations"))
    assert response.status_code == 403
    assert response.json() == {"code": "session_restricted"}


def test_premiere_connexion_de_cheikh(api_client, invite, django_capture_on_commit_callbacks):
    """Parcours : invitation, puis première connexion OTP qui renvoie l'invitation en attente."""
    invitation = invite(hint="Cheikh")
    assert not User.objects.filter(phone=CHEIKH).exists()
    with django_capture_on_commit_callbacks(execute=True):
        challenge = request_code(api_client, CHEIKH, app="pro").json()
    code = FakeSmsGateway.outbox[-1].body.split(" est ")[1][:6]
    response = verify(api_client, challenge, code, app="pro")
    assert response.status_code == 200
    body = response.json()
    assert body["is_new_user"] is True
    assert [i["public_id"] for i in body["pending_invitations"]] == [str(invitation.public_id)]
    assert body["pending_invitations"][0]["display_name_hint"] == "Cheikh"
