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
def owner_factory(complete_user_factory):
    """Un gérant : seul rôle autorisé à inviter (revue sécurité, I1)."""

    def _owner(**kwargs):
        owner = complete_user_factory(**kwargs)
        grant_role(user=owner, role=Role.OWNER, reason_code="test")
        return owner

    return _owner


@pytest.fixture
def fatou(owner_factory):
    return owner_factory(display_name="Fatou Nettoyage")


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


@pytest.fixture(autouse=True)
def handlers(monkeypatch):
    """Registre isolé, avec un gestionnaire factice par rôle : providers n'existe pas encore."""
    registry: dict = {Role.OWNER: lambda accepted: None, Role.TECHNICIAN: lambda accepted: None}
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


def test_deux_sms_d_invitation_par_numero_et_par_jour(invite, owner_factory):
    """Un pro ne peut pas épuiser le budget SMS de connexion d'un numéro avec des invitations."""
    for _ in range(3):
        invite(context_ref=uuid.uuid4(), by=owner_factory())
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


def test_les_sms_d_invitation_comptent_dans_le_budget_du_numero(invite, owner_factory):
    invite(context_ref=uuid.uuid4(), by=owner_factory())
    invite(context_ref=uuid.uuid4(), by=owner_factory())
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
    handlers[Role.TECHNICIAN] = received.append
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

    handlers[Role.TECHNICIAN] = refuse
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
    # Le compte de revue ne voit aucune invitation d'un vrai pro (revue tâche 17, M5).
    with pytest.raises(DomainError) as exc:
        accept_invitation(user=cheikh, invitation_public_id=invitation.public_id)
    assert exc.value.code == "not_found"
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
    handlers.clear()

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
    assert client.post(url).status_code == 204  # rejouée : même succès (I4)
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


# --- Corrections de la revue sécurité (tâche 12) -----------------------------------------------


@pytest.mark.parametrize("kind", ["client", "technicien", "revue"])
def test_seul_un_gerant_invite(invite, complete_user_factory, kind):
    """I1 : un compte sans rôle owner (ou compte de revue) ne fait naître aucun pro."""
    inviter = complete_user_factory(is_review_account=kind == "revue")
    if kind == "technicien":
        grant_role(user=inviter, role=Role.TECHNICIAN, reason_code="test")
    with pytest.raises(DomainError) as exc:
        invite(by=inviter, role=Role.OWNER)
    assert (exc.value.code, exc.value.status_code) == ("role_required", 403)
    assert not RoleInvitation.objects.exists()
    assert FakeSmsGateway.outbox == []


def test_gerant_revoque_ses_invitations_tombent(invite, fatou, complete_user_factory):
    """I1 : Fatou perd son rôle de gérant ; ses invitations en attente ne sont plus acceptables."""
    from jeflink.accounts.services import revoke_role

    cheikh = complete_user_factory(phone=CHEIKH)
    invitation = invite()
    revoke_role(user=fatou, role=Role.OWNER, reason_code="fraud")
    invitation.refresh_from_db()
    assert (invitation.status, invitation.phone) == ("expired", "")
    with pytest.raises(DomainError) as exc:
        accept_invitation(user=cheikh, invitation_public_id=invitation.public_id)
    assert exc.value.code == "not_found"
    assert not cheikh.role_grants.exists()


def test_invitation_d_un_gerant_sans_role_invisible(invite, fatou, complete_user_factory):
    """I1 : même sans passer par revoke_role, le sélecteur exige un gérant actif."""
    cheikh = complete_user_factory(phone=CHEIKH)
    invite()
    RoleGrant.objects.filter(user=fatou).update(revoked_at=timezone.now())
    from jeflink.accounts.selectors import pending_invitations_for

    assert not pending_invitations_for(cheikh).exists()


def test_sans_gestionnaire_providers_rien_n_est_accorde(invite, complete_user_factory, handlers):
    """I2 : sans providers, aucun rôle global détaché d'une équipe."""
    handlers.clear()
    cheikh = complete_user_factory(phone=CHEIKH)
    invitation = invite()
    with pytest.raises(DomainError) as exc:
        accept_invitation(user=cheikh, invitation_public_id=invitation.public_id)
    assert (exc.value.code, exc.value.status_code) == ("invitation_unavailable", 503)
    invitation.refresh_from_db()
    assert invitation.status == "pending"
    assert not cheikh.role_grants.exists()


def test_invitations_d_un_bloc_laissent_intact_son_budget_de_connexion(invite, settings):
    """I3 : 20 invitations vers un même bloc de 1 000 numéros ne consomment que le sous-budget."""
    for n in range(20):
        invite(f"+221781234{n:03d}")
    assert RoleInvitation.objects.count() == 20
    assert len(FakeSmsGateway.outbox) == settings.SMS_NOTICE_BLOCK_HOURLY_CAP
    # Le bloc garde presque tout son budget de connexion.
    for n in range(settings.SMS_BLOCK_HOURLY_CAP - settings.SMS_NOTICE_BLOCK_HOURLY_CAP):
        reserve_sms(phone=f"+221781234{900 + n}", region="SN", new_challenge=False)


def test_pas_de_sms_d_information_au_dela_de_la_moitie_d_un_plafond(invite, settings):
    """I3 : la marge des plafonds partagés reste aux connexions."""
    settings.SMS_BLOCK_HOURLY_CAP = 4
    for n in range(2):
        reserve_sms(phone=f"+22178123450{n}", region="SN", new_challenge=False)
    invitation = invite()
    assert invitation.status == "pending"
    assert FakeSmsGateway.outbox == []


def test_accepter_deux_fois_renvoie_le_meme_succes(api_client, invite, complete_user_factory):
    """I4 : réponse perdue sur réseau faible, l'app rejoue : 204, rien n'est réécrit."""
    cheikh = complete_user_factory(phone=CHEIKH)
    client = bearer(api_client, cheikh)
    invitation = invite()
    url = reverse("me-invitation-accept", args=[invitation.public_id])
    assert client.post(url, {}, format="json").status_code == 204
    assert client.post(url, {}, format="json").status_code == 204
    assert cheikh.role_grants.count() == 1
    assert AuditEvent.objects.filter(action="accounts.invitation.accepted").count() == 1
    # L'acceptation d'un autre compte reste invisible (S5).
    other = bearer(api_client, complete_user_factory(phone="+221770000001"))
    assert other.post(url, {}, format="json").status_code == 404


def test_refuser_deux_fois_renvoie_le_meme_succes(api_client, invite, complete_user_factory):
    client = bearer(api_client, complete_user_factory(phone=CHEIKH))
    url = reverse("me-invitation-decline", args=[invite().public_id])
    assert client.post(url).status_code == 204
    assert client.post(url).status_code == 204
    other = bearer(api_client, complete_user_factory(phone="+221770000001"))
    assert other.post(url).status_code == 404


def test_audit_de_creation_et_de_refus_sans_numero(invite, user_factory):
    """M2 : création et refus tracés, numéro seulement en HMAC."""
    from jeflink.common.pii import phone_hmac

    cheikh = user_factory(phone=CHEIKH)
    invitation = invite()
    created = AuditEvent.objects.get(action="accounts.invitation.created")
    assert created.metadata == {
        "role": "technician",
        "invitation": str(invitation.public_id),
        "phone_hmac": phone_hmac(CHEIKH),
        "sms_queued": True,
    }
    decline_invitation(user=cheikh, invitation_public_id=invitation.public_id)
    assert AuditEvent.objects.filter(action="accounts.invitation.declined").count() == 1
    assert CHEIKH not in str(list(AuditEvent.objects.values_list("metadata", flat=True)))


def test_apres_un_refus_le_meme_pro_n_envoie_plus_de_sms(invite, user_factory, owner_factory):
    """M2 : pas de harcèlement par SMS en changeant d'équipe après un refus."""
    cheikh = user_factory(phone=CHEIKH)
    decline_invitation(user=cheikh, invitation_public_id=invite().public_id)
    invite(context_ref=uuid.uuid4())
    assert len(FakeSmsGateway.outbox) == 1
    # Un autre gérant n'est pas concerné.
    invite(context_ref=uuid.uuid4(), by=owner_factory())
    assert len(FakeSmsGateway.outbox) == 2


def test_broker_indisponible_invitation_creee_sans_erreur(invite, monkeypatch):
    """M4 : le SMS est au mieux ; une panne du broker n'est jamais une 500 pour le pro."""

    def broken(*args, **kwargs):
        raise ConnectionError("broker")

    monkeypatch.setattr(tasks.send_notice_sms, "delay", broken)
    assert invite().status == "pending"
    assert NoticeSms.objects.get().status == "queued"


def test_nom_saisi_a_l_acceptation(api_client, invite, user_factory):
    """M6 : l'invité confirme ou corrige le nom proposé par le pro."""
    cheikh = user_factory(phone=CHEIKH)
    invitation = invite(hint="Cheikh")
    response = bearer(api_client, cheikh).post(
        reverse("me-invitation-accept", args=[invitation.public_id]),
        {"display_name": "Cheikh Ndiaye"},
        format="json",
    )
    assert response.status_code == 204
    cheikh.refresh_from_db()
    assert cheikh.display_name == "Cheikh Ndiaye"


def test_role_non_autorise_en_403(complete_user_factory):
    """M5 : role_not_allowed est un 403 (contrat OpenAPI)."""
    with pytest.raises(DomainError) as exc:
        grant_role(user=complete_user_factory(is_staff=True), role=Role.OWNER, reason_code="t")
    assert (exc.value.code, exc.value.status_code) == ("role_not_allowed", 403)
