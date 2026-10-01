"""Tâche 21 : second facteur et limite de débit de l'admin Django."""

from io import StringIO

import pyotp
import pytest
from django.contrib import admin
from django.contrib.auth.models import Group
from django.core.management import CommandError, call_command
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from jeflink.accounts.admin_site import JeflinkAdminSite
from jeflink.accounts.models import Role, TotpDevice, User
from jeflink.accounts.services import grant_role
from jeflink.trust.models import AuditEvent

from .mfa_helpers import enroll

pytestmark = pytest.mark.django_db(transaction=True, databases="__all__", serialized_rollback=True)

PHONE = "+221770000099"
PASSWORD = "mot-de-passe-long-et-unique-42"


@pytest.fixture
def staff():
    return User.objects.create_superuser(PHONE, PASSWORD)


def code_for(totp, offset=0):
    return totp.at(timezone.now().timestamp() + 30 * offset)


def login(client, code, *, password=PASSWORD, ip="10.1.2.3"):
    return client.post(
        reverse("admin:login"),
        {"username": PHONE, "password": password, "otp_code": code},
        REMOTE_ADDR=ip,
    )


def test_site_admin_par_defaut():
    assert isinstance(admin.site, JeflinkAdminSite)


def test_connexion_avec_code(staff):
    totp = enroll(staff)
    client = Client()
    response = login(client, code_for(totp))
    assert response.status_code == 302
    assert client.get(reverse("admin:index")).status_code == 200
    assert AuditEvent.objects.filter(action="accounts.admin.logged_in").count() == 1


@pytest.mark.parametrize("case", ["code_faux", "sans_code", "mauvais_mot_de_passe"])
def test_connexion_refusee(staff, case):
    totp = enroll(staff)
    client = Client()
    code = {"code_faux": "000000", "sans_code": "", "mauvais_mot_de_passe": code_for(totp)}[case]
    password = "faux" if case == "mauvais_mot_de_passe" else PASSWORD
    response = login(client, code, password=password)
    assert response.status_code == 200
    assert "Identifiants ou code invalides." in response.content.decode()
    assert client.get(reverse("admin:index")).status_code == 302


def test_echec_compte_et_audite(staff):
    enroll(staff)
    login(Client(), "000000")
    event = AuditEvent.objects.get(action="accounts.mfa.failed")
    assert event.metadata == {"stage": "admin", "locked": False}
    assert len(TotpDevice.objects.get().recent_failures) == 1


def test_code_rejoue_refuse(staff):
    totp = enroll(staff)
    code = code_for(totp)
    assert login(Client(), code).status_code == 302
    assert login(Client(), code).status_code == 200


def test_sans_appareil_aucune_connexion(staff):
    assert login(Client(), "123456").status_code == 200


def test_session_sans_second_facteur_refusee(staff):
    """Une connexion forcée (ou ouverte ailleurs) ne suffit pas : le code doit être validé."""
    client = Client()
    client.force_login(staff)
    response = client.get(reverse("admin:index"))
    assert response.status_code == 302
    assert reverse("admin:login") in response["Location"]


def test_dix_echecs_verrouillent(staff, settings):
    totp = enroll(staff)
    for n in range(10):
        login(Client(), "000000", ip=f"10.9.0.{n}")
    assert TotpDevice.objects.get().locked_at is not None
    from jeflink.common.ratelimit import client as redis_client

    redis_client().flushdb()  # hors limite de débit : seul le verrou du TOTP joue
    assert login(Client(), code_for(totp), ip="10.9.1.1").status_code == 200


def test_limite_par_ip(staff):
    for _ in range(10):
        login(Client(), "000000", password="faux")
    response = login(Client(), "000000", password="faux")
    assert response.status_code == 429
    assert int(response["Retry-After"]) > 0


def test_limite_par_identifiant(staff):
    for n in range(10):
        login(Client(), "000000", password="faux", ip=f"10.8.0.{n}")
    assert login(Client(), "000000", password="faux", ip="10.8.1.1").status_code == 429


def test_redis_coupe_refus(staff, redis_down):
    assert login(Client(), "000000").status_code == 503


# --- Enrôlement ----------------------------------------------------------------------------------


@pytest.fixture
def admins(user_factory):
    first, second = user_factory(), user_factory()
    for member in (first, second):
        grant_role(user=member, role=Role.OPS, reason_code="t", operator="a", second_operator="b")
        member.groups.add(Group.objects.get(name="Admin"))
    return first, second


def enroll_cmd(admins, target, *extra):
    out = StringIO()
    call_command(
        "enroll_admin_totp", "--user", str(target.public_id),
        "--operator", str(admins[0].public_id), "--second-operator", str(admins[1].public_id),
        "--reason", "new_staff", *extra, stdout=out,
    )  # fmt: skip
    return out.getvalue()


def test_enrolement_par_commande_puis_premier_code(admins, staff, tmp_path, monkeypatch):
    from django.core.management.base import OutputWrapper

    monkeypatch.setattr(OutputWrapper, "isatty", lambda self: False)
    path = tmp_path / "uri.txt"
    out = enroll_cmd(admins, staff, "--token-file", str(path))
    uri = path.read_text().strip()
    assert uri.startswith("otpauth://totp/Jeflink:") and uri not in out
    assert PHONE[1:] not in uri
    device = TotpDevice.objects.get(user=staff)
    assert device.confirmed_at is None
    totp = pyotp.parse_uri(uri)
    assert login(Client(), totp.now()).status_code == 302
    device.refresh_from_db()
    assert device.confirmed_at is not None
    assert AuditEvent.objects.filter(action="accounts.admin.totp_issued").exists()


def test_enrolement_refuse_hors_compte_technique(admins, user_factory, monkeypatch):
    from django.core.management.base import OutputWrapper

    monkeypatch.setattr(OutputWrapper, "isatty", lambda self: True)
    with pytest.raises(CommandError):
        enroll_cmd(admins, user_factory())
