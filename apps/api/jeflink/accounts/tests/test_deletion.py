"""Tâche 14 : suppression du compte (S16) et « Repartir de zéro » (compte dormant, S18)."""

import uuid
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from jeflink.accounts import deletion
from jeflink.accounts.models import DeviceSession, OtpChallenge, Role, RoleInvitation, User
from jeflink.accounts.services import grant_role, invite_to_role
from jeflink.accounts.sessions import create_session
from jeflink.notifications.sms.fake import FakeSmsGateway
from jeflink.trust.models import AuditEvent

from .otp_helpers import INSTALL_A, last_code, request_code, verify

# Échecs et refus audités hors transaction (connexion « audit ») : tests transactionnels.
pytestmark = pytest.mark.django_db(transaction=True, databases="__all__", serialized_rollback=True)

PHONE = "+221771234567"


@pytest.fixture(autouse=True)
def registries(monkeypatch):
    """Registres isolés : les tests ajoutent leurs anonymiseurs et bloqueurs."""
    monkeypatch.setattr(deletion, "_ANONYMIZERS", {})
    monkeypatch.setattr(deletion, "_BLOCKERS", {"accounts": deletion._accounts_blockers})


@pytest.fixture
def awa(complete_user_factory):
    return complete_user_factory(phone=PHONE, display_name="Awa Diop", email="awa@exemple.sn")


def bearer(api_client, user, **kwargs):
    kwargs.setdefault("app", "client")
    kwargs.setdefault("platform", "android")
    pair = create_session(user=user, device_label="Samsung A05", install_id=INSTALL_A, **kwargs)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {pair.access}")
    return api_client, pair


def ask_deletion(client, key=None):
    return client.post(reverse("me-deletion-otp"), HTTP_IDEMPOTENCY_KEY=key or uuid.uuid4().hex)


def confirm(client, challenge, code):
    return client.post(
        reverse("me-deletion"),
        {
            "challenge_id": challenge["challenge_id"],
            "challenge_secret": challenge["challenge_secret"],
            "code": code,
        },
        format="json",
    )


# --- Suppression --------------------------------------------------------------------------------


def test_suppression_anonymise_et_libere_le_numero(api_client, awa):
    grant_role(user=awa, role=Role.TECHNICIAN, reason_code="test")
    client, pair = bearer(api_client, awa)
    challenge = ask_deletion(client).json()
    sms = FakeSmsGateway.outbox[-1]
    assert sms.to == PHONE and "SUPPRIMER" in sms.body
    assert confirm(client, challenge, last_code()).status_code == 204

    awa.refresh_from_db()
    assert awa.phone is None
    assert (awa.display_name, awa.email, awa.is_active) == ("", "", False)
    assert awa.deleted_at is not None
    assert not awa.has_usable_password()
    session = DeviceSession.objects.get(pk=pair.session.pk)
    assert session.revoked_reason == "account_deleted"
    assert (session.device_label, session.install_id) == ("", "")
    assert not awa.role_grants.filter(revoked_at__isnull=True).exists()
    assert not OtpChallenge.objects.filter(phone=PHONE).exists()
    event = AuditEvent.objects.get(action="accounts.user.deleted")
    assert event.metadata == {"reason": "user_request"}
    assert PHONE not in str(list(AuditEvent.objects.values_list("metadata", flat=True)))

    # L'accès de la session supprimée est refusé immédiatement.
    assert client.get(reverse("me")).status_code == 401
    # Le numéro est libre : une nouvelle connexion crée un compte neuf.
    api_client.credentials()
    fresh = request_code(api_client, PHONE).json()
    body = verify(api_client, fresh, last_code()).json()
    assert body["is_new_user"] is True
    assert body["user"]["public_id"] != str(awa.public_id)


def test_invitations_vers_le_numero_effacees(api_client, awa, complete_user_factory):
    owner = complete_user_factory()
    grant_role(user=owner, role=Role.OWNER, reason_code="test")
    invite_to_role(phone=PHONE, role="technician", invited_by=owner, context_ref=uuid.uuid4())
    client, _ = bearer(api_client, awa)
    challenge = ask_deletion(client).json()
    assert confirm(client, challenge, last_code()).status_code == 204
    # Closes, pas supprimées : quota et audit du pro restent cohérents (revue, M4).
    invitation = RoleInvitation.objects.get()
    assert (invitation.status, invitation.phone) == ("expired", "")


def test_gerant_supprime_ses_invitations_envoyees_closes(api_client, complete_user_factory):
    owner = complete_user_factory()
    grant_role(user=owner, role=Role.OWNER, reason_code="test")
    invitation = invite_to_role(
        phone="+221781111111", role="technician", invited_by=owner, context_ref=uuid.uuid4()
    )
    client, _ = bearer(api_client, owner)
    challenge = ask_deletion(client).json()
    assert confirm(client, challenge, last_code()).status_code == 204
    invitation.refresh_from_db()
    assert (invitation.status, invitation.phone) == ("expired", "")


def test_code_de_connexion_refuse_pour_supprimer(api_client, awa):
    """S16 : purpose strict. Un code de connexion ne supprime jamais un compte."""
    login = request_code(api_client, PHONE).json()
    client, _ = bearer(api_client, awa)
    response = confirm(client, login, last_code())
    assert response.status_code == 400
    assert response.json() == {"code": "otp_challenge_invalid"}
    awa.refresh_from_db()
    assert awa.is_active


def test_challenge_d_un_autre_compte_refuse(api_client, awa, user_factory):
    other_client, _ = bearer(api_client.__class__(), user_factory())
    challenge = ask_deletion(other_client).json()
    code = last_code()
    client, _ = bearer(api_client, awa)
    assert confirm(client, challenge, code).json() == {"code": "otp_challenge_invalid"}


def test_mauvais_code(api_client, awa):
    client, _ = bearer(api_client, awa)
    challenge = ask_deletion(client).json()
    code = f"{(int(last_code()) + 1) % 10**6:06d}"
    response = confirm(client, challenge, code)
    assert response.status_code == 400
    assert response.json()["code"] == "otp_invalid"
    awa.refresh_from_db()
    assert awa.is_active and awa.phone == PHONE


def test_meme_cle_d_idempotence_un_seul_sms(api_client, awa):
    client, _ = bearer(api_client, awa)
    key = uuid.uuid4().hex
    first = ask_deletion(client, key).json()
    assert ask_deletion(client, key).json() == first
    assert len(FakeSmsGateway.outbox) == 1


def test_bloqueur_refuse_sans_sms(api_client, awa):
    deletion.register_deletion_blocker("bookings", lambda user: "booking_in_progress")
    client, _ = bearer(api_client, awa)
    response = ask_deletion(client)
    assert response.status_code == 409
    assert response.json() == {
        "code": "account_deletion_blocked",
        "reasons": ["booking_in_progress"],
    }
    assert FakeSmsGateway.outbox == []
    event = AuditEvent.objects.get(action="accounts.deletion.blocked")
    assert event.metadata == {"reasons": ["booking_in_progress"]}


def test_bloqueur_apparu_entre_le_code_et_la_confirmation(api_client, awa):
    client, _ = bearer(api_client, awa)
    challenge = ask_deletion(client).json()
    deletion.register_deletion_blocker("wallet", lambda user: "wallet_balance")
    response = confirm(client, challenge, last_code())
    assert response.status_code == 409
    awa.refresh_from_db()
    assert awa.is_active


def test_compte_ops_bloque(api_client, user_factory):
    ops = user_factory()
    grant_role(user=ops, role=Role.OPS, reason_code="t", operator="a", second_operator="b")
    client, _ = bearer(api_client, ops)
    assert ask_deletion(client).json()["reasons"] == ["ops_role"]


def test_anonymiseur_appele_avant_l_effacement_du_numero(api_client, awa):
    seen = []
    deletion.register_anonymizer("requests", lambda user: seen.append(user.phone))
    client, _ = bearer(api_client, awa)
    challenge = ask_deletion(client).json()
    assert confirm(client, challenge, last_code()).status_code == 204
    assert seen == [PHONE]


def test_anonymiseur_en_erreur_annule_tout(api_client, awa):
    def broken(user):
        raise RuntimeError("panne")

    deletion.register_anonymizer("requests", broken)
    client, _ = bearer(api_client, awa)
    challenge = ask_deletion(client).json()
    with pytest.raises(RuntimeError):
        confirm(client, challenge, last_code())
    awa.refresh_from_db()
    assert awa.is_active and awa.phone == PHONE


def test_registre_refuse_un_doublon():
    deletion.register_anonymizer("requests", print)
    deletion.register_anonymizer("requests", print)  # idempotent
    with pytest.raises(ValueError):
        deletion.register_anonymizer("requests", repr)


def test_session_restreinte_ne_supprime_pas(api_client, awa):
    client, _ = bearer(api_client, awa, restricted=True)
    response = ask_deletion(client)
    assert response.status_code == 403
    assert response.json() == {"code": "session_restricted"}


# --- « Repartir de zéro » -----------------------------------------------------------------------


def test_repartir_de_zero(api_client, awa, complete_user_factory):
    owner = complete_user_factory()
    grant_role(user=owner, role=Role.OWNER, reason_code="test")
    invitation = invite_to_role(
        phone=PHONE, role="technician", invited_by=owner, context_ref=uuid.uuid4()
    )
    client, pair = bearer(api_client, awa, restricted=True)
    response = client.post(reverse("me-fresh-start"))
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "authenticated"
    assert body["is_new_user"] is True and body["restricted"] is False
    assert body["user"]["display_name"] == ""
    # Les invitations vers ce numéro visent son titulaire actuel : elles restent.
    assert [i["public_id"] for i in body["pending_invitations"]] == [str(invitation.public_id)]

    awa.refresh_from_db()
    assert awa.phone is None and awa.deleted_at is not None
    assert AuditEvent.objects.get(action="accounts.user.deleted").metadata == {
        "reason": "fresh_start"
    }
    new = User.objects.get(phone=PHONE)
    assert new.pk != awa.pk and new.dormant_restricted_since is None
    session = DeviceSession.objects.get(user=new)
    assert not session.restricted and session.install_id == INSTALL_A
    pair.session.refresh_from_db()
    assert pair.session.revoked_at is not None


def test_repartir_de_zero_refuse_a_un_pro(api_client, awa):
    grant_role(user=awa, role=Role.TECHNICIAN, reason_code="test")
    client, _ = bearer(api_client, awa, app="pro", restricted=True)
    response = client.post(reverse("me-fresh-start"))
    assert response.status_code == 403
    assert response.json() == {"code": "fresh_start_not_allowed"}
    awa.refresh_from_db()
    assert awa.is_active


def test_repartir_de_zero_refuse_hors_session_restreinte(api_client, awa):
    client, _ = bearer(api_client, awa)
    assert client.post(reverse("me-fresh-start")).json() == {"code": "fresh_start_not_allowed"}


def test_repartir_de_zero_exige_une_connexion_recente(api_client, awa):
    client, pair = bearer(api_client, awa, restricted=True)
    DeviceSession.objects.filter(pk=pair.session.pk).update(
        auth_time=timezone.now() - timedelta(hours=1)
    )
    from jeflink.accounts.sessions import refresh_session

    access = refresh_session(pair.refresh).access
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    assert client.post(reverse("me-fresh-start")).json() == {"code": "reauth_required"}


# --- Corrections de la revue sécurité (tâche 14) -----------------------------------------------


def _blocker_on_second_call(reason):
    calls = []

    def blocker(user):
        calls.append(user.pk)
        return reason if len(calls) >= 2 else None

    return blocker


def test_refus_decide_sous_verrou_jamais_recalcule(api_client, awa):
    """I1 : un bloqueur qui ne répond que sous verrou donne 409, jamais 204 sans suppression."""
    client, _ = bearer(api_client, awa)
    challenge = ask_deletion(client).json()
    deletion.register_deletion_blocker("wallet", _blocker_on_second_call("wallet_balance"))
    response = confirm(client, challenge, last_code())
    assert response.status_code == 409
    assert response.json() == {"code": "account_deletion_blocked", "reasons": ["wallet_balance"]}
    awa.refresh_from_db()
    assert awa.is_active and awa.phone == PHONE
    assert AuditEvent.objects.filter(action="accounts.deletion.blocked").count() == 1
    # Le code a servi : le rejouer ne supprime rien.
    assert confirm(client, challenge, last_code()).status_code == 409


def test_repartir_de_zero_bloque_sous_verrou(api_client, awa):
    """I1 : 409, jamais 500."""
    deletion.register_deletion_blocker("wallet", lambda user: "wallet_balance")
    client, _ = bearer(api_client, awa, restricted=True)
    response = client.post(reverse("me-fresh-start"))
    assert response.status_code == 409
    assert response.json()["reasons"] == ["wallet_balance"]
    awa.refresh_from_db()
    assert awa.is_active


def test_refus_audite_une_fois_par_heure(api_client, awa):
    """M6 : un compte bloqué n'inonde pas l'audit."""
    deletion.register_deletion_blocker("bookings", lambda user: "booking_in_progress")
    client, _ = bearer(api_client, awa)
    for _ in range(3):
        assert ask_deletion(client).status_code == 409
    assert AuditEvent.objects.filter(action="accounts.deletion.blocked").count() == 1


def test_code_de_suppression_refuse_par_la_connexion(api_client, awa):
    """S16 : un code de suppression n'ouvre jamais de session."""
    client, _ = bearer(api_client, awa)
    challenge = ask_deletion(client).json()
    api_client.credentials()
    response = verify(api_client, challenge, last_code())
    assert response.json() == {"code": "otp_challenge_invalid"}


def test_numero_change_entre_le_code_et_la_suppression(api_client, awa):
    """M9 : le code visait l'ancien numéro du compte."""
    client, _ = bearer(api_client, awa)
    challenge = ask_deletion(client).json()
    code = last_code()
    User.objects.filter(pk=awa.pk).update(phone="+221779999999")
    assert confirm(client, challenge, code).json() == {"code": "otp_challenge_invalid"}
    awa.refresh_from_db()
    assert awa.is_active


def test_refresh_refuse_apres_suppression(api_client, awa):
    from jeflink.accounts.sessions import refresh_session
    from jeflink.common.errors import DomainError

    client, pair = bearer(api_client, awa)
    challenge = ask_deletion(client).json()
    assert confirm(client, challenge, last_code()).status_code == 204
    with pytest.raises(DomainError) as exc:
        refresh_session(pair.refresh)
    assert exc.value.code == "session_revoked"


def test_repartir_de_zero_efface_codes_et_nom_propose(api_client, awa, complete_user_factory):
    """M7 : le nom proposé (peut-être celui de l'ancien titulaire) n'est pas transmis."""
    owner = complete_user_factory()
    grant_role(user=owner, role=Role.OWNER, reason_code="test")
    invite_to_role(
        phone=PHONE,
        role="technician",
        invited_by=owner,
        context_ref=uuid.uuid4(),
        display_name_hint="Awa",
    )
    OtpChallenge.objects.create(
        phone=PHONE,
        region="SN",
        purpose="login",
        challenge_secret_hash="x",
        app="client",
        expires_at=timezone.now() + timedelta(minutes=30),
    )
    client, pair = bearer(api_client, awa, restricted=True)
    assert client.post(reverse("me-fresh-start")).status_code == 200
    assert not OtpChallenge.objects.filter(phone=PHONE).exists()
    assert RoleInvitation.objects.get().display_name_hint == ""
    event = AuditEvent.objects.get(action="accounts.user.deleted")
    assert event.session_public_id == pair.session.public_id
