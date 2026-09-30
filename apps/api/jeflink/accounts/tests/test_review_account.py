"""Tâche 17 : compte de revue des stores (S17)."""

import uuid
from datetime import timedelta
from io import StringIO

import pytest
from django.contrib.auth.models import Group
from django.core.management import CommandError, call_command
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from jeflink.accounts.checks import review_accounts, review_settings
from jeflink.accounts.models import DeviceSession, ReviewAccess, Role, User
from jeflink.accounts.services import grant_role
from jeflink.accounts.sessions import create_session
from jeflink.common.errors import DomainError
from jeflink.notifications.sms.fake import FakeSmsGateway
from jeflink.trust.models import AuditEvent

from .otp_helpers import INSTALL_A, last_code, request_code, verify

pytestmark = pytest.mark.django_db(transaction=True, databases="__all__", serialized_rollback=True)

REVIEW = "+221770000042"


@pytest.fixture(autouse=True)
def review_window(settings):
    settings.OTP_REVIEW_ACCOUNTS = [REVIEW]
    settings.OTP_REVIEW_ENABLED_UNTIL = (timezone.now() + timedelta(days=10)).isoformat()


@pytest.fixture(autouse=True)
def terminal(monkeypatch):
    from django.core.management.base import OutputWrapper

    monkeypatch.setattr(OutputWrapper, "isatty", lambda self: True)


@pytest.fixture
def admins(user_factory):
    first, second = user_factory(), user_factory()
    for admin in (first, second):
        grant_role(user=admin, role=Role.OPS, reason_code="t", operator="a", second_operator="b")
        admin.groups.add(Group.objects.get(name="Admin"))
    return first, second


def create(admins, *extra, reason="store_submission"):
    out = StringIO()
    call_command(
        "create_review_account",
        "--phone", REVIEW,
        "--operator", str(admins[0].public_id),
        "--second-operator", str(admins[1].public_id),
        "--reason", reason,
        *extra,
        stdout=out,
    )  # fmt: skip
    return out.getvalue().rsplit(" : ", 1)[1].strip()


def login(code, *, app="client"):
    client = APIClient()
    challenge = request_code(client, REVIEW, app=app).json()
    return verify(client, challenge, code, app=app)


# --- Commande ------------------------------------------------------------------------------------


def test_creation_et_code(admins):
    code = create(admins)
    assert len(code) == 6 and code.isdigit()
    user = User.objects.get(phone=REVIEW)
    assert user.is_review_account and user.profile_status == "complete"
    assert ReviewAccess.objects.get(user=user).code_hash != code
    actions = list(AuditEvent.objects.values_list("action", flat=True))
    assert "accounts.review_account.created" in actions
    assert "accounts.review_account.code_rotated" in actions


def test_nouveau_code_a_chaque_soumission(admins):
    first = create(admins)
    second = create(admins, reason="code_rotation")
    assert login(first).json()["code"] == "otp_invalid"
    assert login(second).status_code == 200


def test_code_ecrit_dans_un_fichier(admins, tmp_path, monkeypatch):
    from django.core.management.base import OutputWrapper

    monkeypatch.setattr(OutputWrapper, "isatty", lambda self: False)
    path = tmp_path / "code.txt"
    out = StringIO()
    call_command(
        "create_review_account", "--phone", REVIEW,
        "--operator", str(admins[0].public_id), "--second-operator", str(admins[1].public_id),
        "--reason", "store_submission", "--token-file", str(path), stdout=out,
    )  # fmt: skip
    code = path.read_text().strip()
    assert code not in out.getvalue()
    assert login(code).status_code == 200


@pytest.mark.parametrize("case", ["numero_non_liste", "compte_reel", "fenetre_fermee"])
def test_commande_refusee(admins, user_factory, settings, case):
    if case == "numero_non_liste":
        settings.OTP_REVIEW_ACCOUNTS = []
    elif case == "compte_reel":
        user_factory(phone=REVIEW)
    else:
        settings.OTP_REVIEW_ENABLED_UNTIL = ""
    with pytest.raises(CommandError):
        create(admins)
    assert not User.objects.filter(phone=REVIEW, is_review_account=True).exists()


def test_commande_exige_deux_admin(admins):
    with pytest.raises(CommandError):
        call_command(
            "create_review_account", "--phone", REVIEW,
            "--operator", str(admins[0].public_id), "--second-operator", str(admins[0].public_id),
            "--reason", "store_submission", stdout=StringIO(),
        )  # fmt: skip
    assert not User.objects.filter(phone=REVIEW).exists()


# --- Connexion ----------------------------------------------------------------------------------


@pytest.mark.parametrize("app", ["client", "pro"])
def test_connexion_de_revue_sans_sms(admins, app):
    code = create(admins)
    response = login(code, app=app)
    assert response.status_code == 200
    assert response.json()["restricted"] is False
    assert FakeSmsGateway.outbox == []
    event = AuditEvent.objects.get(action="accounts.review_account.used")
    assert event.metadata == {"app": app, "purpose": "login"}


def test_mauvais_code_compte(admins):
    create(admins)
    response = login("000000")
    body = response.json()
    assert body["code"] == "otp_invalid" and body["attempts_remaining"] == 4


def test_fenetre_fermee_compte_ferme(admins, settings):
    create(admins)
    settings.OTP_REVIEW_ENABLED_UNTIL = (timezone.now() - timedelta(minutes=1)).isoformat()
    client = APIClient()
    challenge = request_code(client, REVIEW).json()
    # Hors fenêtre : SMS normal vers la SIM Jeflink, et le compte de revue refuse la connexion.
    assert FakeSmsGateway.outbox[-1].to == REVIEW
    response = verify(client, challenge, last_code())
    assert response.json() == {"code": "account_not_allowed"}


def test_numero_de_revue_ne_cree_jamais_de_compte():
    client = APIClient()
    challenge = request_code(client, REVIEW).json()
    code = last_code()  # SMS normal : aucun compte de revue sur ce numéro
    assert verify(client, challenge, code).json() == {"code": "account_not_allowed"}
    assert not User.objects.filter(phone=REVIEW).exists()


def test_compte_de_revue_jamais_dormant(admins):
    code = create(admins)
    user = User.objects.get(phone=REVIEW)
    User.objects.filter(pk=user.pk).update(created_at=timezone.now() - timedelta(days=200))
    create_session(user=user, app="client", platform="android", install_id=str(uuid.uuid4()))
    DeviceSession.objects.update(last_seen_at=timezone.now() - timedelta(days=90))
    assert login(code).json()["restricted"] is False


def test_rejeu_de_verify_avec_le_code_de_revue(admins):
    code = create(admins)
    client = APIClient()
    challenge = request_code(client, REVIEW).json()
    first = verify(client, challenge, code, install_id=INSTALL_A)
    again = verify(client, challenge, code, install_id=INSTALL_A)
    assert first.status_code == again.status_code == 200


def test_aucun_role_sur_le_compte_de_revue(admins):
    create(admins)
    with pytest.raises(DomainError) as exc:
        grant_role(user=User.objects.get(phone=REVIEW), role=Role.OWNER, reason_code="t")
    assert exc.value.code == "role_not_allowed"


# --- Suppression par l'équipe de revue ----------------------------------------------------------


def test_suppression_par_l_equipe_de_revue(admins):
    code = create(admins)
    tokens = login(code).json()["tokens"]
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    challenge = client.post(
        reverse("me-deletion-otp"), HTTP_IDEMPOTENCY_KEY=uuid.uuid4().hex
    ).json()
    assert FakeSmsGateway.outbox == []
    response = client.post(
        reverse("me-deletion"),
        {
            "challenge_id": challenge["challenge_id"],
            "challenge_secret": challenge["challenge_secret"],
            "code": code,
        },
        format="json",
    )
    assert response.status_code == 204
    assert not ReviewAccess.objects.exists()
    # Plus de compte de revue : le code de revue ne vaut plus (SMS normal vers la SIM Jeflink),
    # et le numéro ne recrée pas de compte. La commande sera relancée à la soumission suivante.
    assert login(code).json()["code"] == "otp_invalid"
    client = APIClient()
    sms_challenge = request_code(client, REVIEW).json()
    assert verify(client, sms_challenge, last_code()).json() == {"code": "account_not_allowed"}


# --- Vérifications au démarrage ------------------------------------------------------------------


def test_check_fenetre_trop_longue_en_production(settings):
    settings.DJANGO_ENV = "production"
    settings.OTP_REVIEW_ENABLED_UNTIL = (timezone.now() + timedelta(days=90)).isoformat()
    assert [e.id for e in review_settings(None)] == ["accounts.E102"]


def test_check_date_invalide(settings):
    settings.OTP_REVIEW_ENABLED_UNTIL = "demain"
    assert [e.id for e in review_settings(None)] == ["accounts.E101"]


def test_check_compte_reel_sur_un_numero_de_revue(user_factory):
    assert review_accounts(None, databases=["default"]) == []
    user_factory(phone=REVIEW)
    assert [e.id for e in review_accounts(None, databases=["default"])] == ["accounts.E105"]
