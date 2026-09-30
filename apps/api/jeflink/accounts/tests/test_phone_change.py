"""Tâche 16 : changement de numéro par l'Ops (S2), confirmé par l'utilisateur."""

from datetime import timedelta

import pytest
from django.conf import settings
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from jeflink.accounts.models import (
    DeviceSession,
    NoticeSms,
    OtpChallenge,
    PhoneChangeRequest,
    Role,
    User,
)
from jeflink.accounts.services import grant_role
from jeflink.accounts.sessions import create_session
from jeflink.notifications.sms.fake import FakeSmsGateway
from jeflink.trust.models import AuditEvent

from .mfa_helpers import enroll
from .otp_helpers import INSTALL_A, last_code, request_code

pytestmark = pytest.mark.django_db(transaction=True, databases="__all__", serialized_rollback=True)

OLD = "+221771234567"
NEW = "+221781234567"


def make_ops(user_factory, group="Admin"):
    user = user_factory()
    grant_role(user=user, role=Role.OPS, reason_code="t", operator="a", second_operator="b")
    user.groups.add(Group.objects.get(name=group))
    enroll(user)
    return user


def console(user):
    pair = create_session(user=user, app="console", platform="web", mfa_verified_at=timezone.now())
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {pair.access}")
    return client


@pytest.fixture
def admin(user_factory):
    return make_ops(user_factory)


@pytest.fixture
def awa(complete_user_factory):
    return complete_user_factory(phone=OLD, display_name="Awa Diop")


def ask(client, target, new=NEW, reason="sim_lost_new_number"):
    return client.post(
        reverse("ops-phone-change", args=[target.public_id]),
        {"new_phone": new, "reason_code": reason},
        format="json",
    )


def confirm(code, phone=NEW, *, client=None):
    return (client or APIClient()).post(
        reverse("auth-phone-change-confirm"),
        {
            "phone": phone,
            "code": code,
            "terms_version": settings.TERMS_VERSION,
            "device": {"platform": "android", "label": "Tecno Spark", "install_id": INSTALL_A},
            "app": "client",
        },
        format="json",
    )


def wrong(code: str) -> str:
    return f"{(int(code) + 1) % 10**6:06d}"


# --- Parcours client -------------------------------------------------------------------------


def test_parcours_client(admin, awa):
    old_session = create_session(user=awa, app="client", platform="android")
    response = ask(console(admin), awa)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "approved" and body["requires_approval"] is False
    assert body["new_phone_masked"] == "+221 •••••••67"
    assert "code" not in body  # l'Ops ne voit jamais le code
    sms = FakeSmsGateway.outbox[-1]
    assert sms.to == NEW and "relier ce numéro" in sms.body

    response = confirm(last_code())
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "authenticated"
    assert result["user"]["public_id"] == str(awa.public_id)

    awa.refresh_from_db()
    assert awa.phone == NEW and awa.phone_changed_at is not None
    old_session.session.refresh_from_db()
    assert old_session.session.revoked_reason == "phone_changed"
    request = PhoneChangeRequest.objects.get()
    assert (request.status, request.new_phone) == ("completed", "")
    # SMS d'information à l'ancien numéro, sans donnée utilisateur.
    info = FakeSmsGateway.outbox[-1]
    assert info.to == OLD and "numéro de votre compte a été changé" in info.body
    assert NoticeSms.objects.get(kind="phone_changed").phone == ""
    actions = set(AuditEvent.objects.values_list("action", flat=True))
    assert {"accounts.phone_change.requested", "accounts.phone_change.completed"} <= actions
    assert OLD not in str(list(AuditEvent.objects.values_list("metadata", flat=True)))
    assert NEW not in str(list(AuditEvent.objects.values_list("metadata", flat=True)))


def test_l_ancien_numero_est_libre(admin, awa):
    ask(console(admin), awa)
    confirm(last_code())
    client = APIClient()
    request_code(client, OLD)
    assert not User.objects.filter(phone=OLD).exists()


def test_compte_dormant_leve_par_le_changement(admin, awa):
    create_session(user=awa, app="client", platform="android", restricted=True)
    ask(console(admin), awa)
    body = confirm(last_code()).json()
    assert body["restricted"] is False
    awa.refresh_from_db()
    assert awa.dormant_restricted_since is None


# --- Compte pro : second Ops (S2) ------------------------------------------------------------


def test_compte_pro_exige_un_second_ops(admin, awa, user_factory):
    grant_role(user=awa, role=Role.OWNER, reason_code="test")
    response = ask(console(admin), awa)
    assert response.json()["status"] == "pending_approval"
    assert FakeSmsGateway.outbox == []  # rien ne part avant l'approbation
    request_id = response.json()["public_id"]

    same = console(admin).post(reverse("ops-pc-approve", args=[request_id]))
    assert same.status_code == 403
    assert same.json() == {"code": "ops_second_operator_required"}

    other = make_ops(user_factory)
    assert console(other).post(reverse("ops-pc-approve", args=[request_id])).status_code == 204
    assert FakeSmsGateway.outbox[-1].to == NEW
    assert confirm(last_code()).status_code == 200
    request = PhoneChangeRequest.objects.get()
    assert (request.requested_by, request.approved_by) == (admin, other)


def test_liste_des_demandes_ouvertes(admin, awa):
    grant_role(user=awa, role=Role.TECHNICIAN, reason_code="test")
    ask(console(admin), awa)
    response = console(admin).get(reverse("ops-phone-changes"))
    assert response.status_code == 200
    [item] = response.json()["results"]
    assert item["status"] == "pending_approval"
    assert item["current_phone_masked"] == "+221 •••••••67"
    assert NEW not in response.content.decode() and OLD not in response.content.decode()


# --- Refus ---------------------------------------------------------------------------------------


def test_groupe_sans_permission(user_factory, awa):
    support = make_ops(user_factory, group="Support")
    assert ask(console(support), awa).json() == {"code": "ops_forbidden"}


@pytest.mark.parametrize(
    ("setup", "new", "code"),
    [
        ("used", NEW, "phone_in_use"),
        ("none", OLD, "phone_unchanged"),
        ("none", "+33612345678", "phone_region_not_supported"),
    ],
)
def test_demandes_refusees(admin, awa, user_factory, setup, new, code):
    if setup == "used":
        user_factory(phone=NEW)
    response = ask(console(admin), awa, new=new)
    assert response.json()["code"] == code
    assert not PhoneChangeRequest.objects.exists()


def test_une_seule_demande_ouverte_par_compte(admin, awa):
    ask(console(admin), awa)
    response = ask(console(admin), awa, new="+221781111111")
    assert response.json() == {"code": "phone_change_in_progress"}


def test_cible_ops_interdite(admin, user_factory):
    other = make_ops(user_factory)
    assert ask(console(admin), other).json() == {"code": "ops_target_forbidden"}


def test_rejet(admin, awa):
    request_id = ask(console(admin), awa).json()["public_id"]
    code = last_code()
    response = console(admin).post(
        reverse("ops-pc-reject", args=[request_id]),
        {"reason_code": "suspected_fraud"},
        format="json",
    )
    assert response.status_code == 204
    request = PhoneChangeRequest.objects.get()
    assert (request.status, request.new_phone) == ("rejected", "")
    assert confirm(code).json() == {"code": "otp_invalid"}


def test_demande_expiree(admin, awa):
    grant_role(user=awa, role=Role.OWNER, reason_code="test")
    request_id = ask(console(admin), awa).json()["public_id"]
    PhoneChangeRequest.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
    response = console(admin).post(
        reverse("ops-pc-reject", args=[request_id]), {"reason_code": "request_error"}, format="json"
    )
    assert response.json() == {"code": "phone_change_closed"}
    # Invisible dans la liste des demandes ouvertes ; la purge la ferme (tâche 18).
    assert console(admin).get(reverse("ops-phone-changes")).json()["results"] == []


# --- Confirmation par l'utilisateur ------------------------------------------------------------


def test_code_faux_ou_numero_inconnu_meme_reponse(admin, awa):
    ask(console(admin), awa)
    code = last_code()
    assert confirm(wrong(code)).json() == {"code": "otp_invalid"}
    assert confirm(code, phone="+221700000000").json() == {"code": "otp_invalid"}
    assert confirm(code).status_code == 200


def test_cinq_echecs_verrouillent_le_code(admin, awa):
    ask(console(admin), awa)
    code = last_code()
    for _ in range(5):
        assert confirm(wrong(code)).json() == {"code": "otp_invalid"}
    assert confirm(code).json() == {"code": "otp_invalid"}
    awa.refresh_from_db()
    assert awa.phone == OLD


def test_code_de_connexion_refuse(admin, awa):
    """Seul un challenge change_phone est accepté."""
    ask(console(admin), awa)
    OtpChallenge.objects.filter(purpose="change_phone").update(status="expired")
    request_code(APIClient(), NEW)
    assert confirm(last_code()).json() == {"code": "otp_invalid"}


def test_renvoi_limite_a_trois_codes(admin, awa):
    client = console(admin)
    request_id = ask(client, awa).json()["public_id"]
    first = last_code()
    for _ in range(2):
        response = client.post(reverse("ops-pc-resend-code", args=[request_id]))
        assert response.status_code == 204
    response = client.post(reverse("ops-pc-resend-code", args=[request_id]))
    assert response.status_code == 429
    assert response.json() == {"code": "phone_change_codes_exhausted"}
    # Seul le dernier code vaut.
    assert confirm(first).json() == {"code": "otp_invalid"}
    assert confirm(last_code()).status_code == 200


def test_suppression_du_compte_ferme_la_demande(admin, awa):
    from jeflink.accounts.deletion import _anonymize

    ask(console(admin), awa)
    _anonymize(User.objects.get(pk=awa.pk), reason="user_request")
    request = PhoneChangeRequest.objects.get()
    assert (request.status, request.new_phone) == ("expired", "")


def test_nouvelle_session_sur_l_appareil_de_confirmation(admin, awa):
    ask(console(admin), awa)
    confirm(last_code())
    session = DeviceSession.objects.get(user=awa, revoked_at__isnull=True)
    assert (session.device_label, session.install_id) == ("Tecno Spark", INSTALL_A)
