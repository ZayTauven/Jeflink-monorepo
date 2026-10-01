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
FULLWIDTH_PLUS = chr(0xFF0B)  # « + » pleine largeur, normalisé par Django (NFKC)


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


# --- Corrections de la revue sécurité (tâche 21) ------------------------------------------------


def logged_in_client(staff):
    totp = enroll(staff)
    client = Client()
    assert login(client, code_for(totp)).status_code == 302
    assert client.get(reverse("admin:index")).status_code == 200
    return client, totp


def test_verrou_ferme_la_session_ouverte(staff):
    """I1 : un TOTP verrouillé ferme aussi les sessions admin déjà ouvertes."""
    client, _ = logged_in_client(staff)
    TotpDevice.objects.update(locked_at=timezone.now())
    assert client.get(reverse("admin:index")).status_code == 302


def test_reenrolement_ferme_la_session_ouverte(staff):
    """I1 : appareil perdu → réenrôlement → l'ancien cookie ne vaut plus."""
    client, _ = logged_in_client(staff)
    TotpDevice.objects.all().delete()
    enroll(staff)
    assert client.get(reverse("admin:index")).status_code == 302


def test_second_facteur_perime(staff, settings):
    client, _ = logged_in_client(staff)
    settings.ADMIN_MFA_MAX_AGE = 0
    assert client.get(reverse("admin:index")).status_code == 302


def test_session_django_courte(settings):
    assert settings.SESSION_COOKIE_AGE <= 12 * 3600


def test_variantes_unicode_du_numero_partagent_la_limite(staff):
    """I2 : chiffres pleine largeur ramenés au même identifiant que Django."""
    fullwidth = "".join(chr(0xFF10 + int(c)) if c.isdigit() else c for c in PHONE[1:])
    for n in range(10):
        variant = (FULLWIDTH_PLUS + fullwidth) if n % 2 else PHONE
        Client().post(
            reverse("admin:login"),
            {"username": variant, "password": "faux", "otp_code": "000000"},
            REMOTE_ADDR=f"10.7.0.{n}",
        )
    response = Client().post(
        reverse("admin:login"),
        {"username": FULLWIDTH_PLUS + fullwidth, "password": "faux", "otp_code": "000000"},
        REMOTE_ADDR="10.7.1.1",
    )
    assert response.status_code == 429


def test_appareil_non_confirme_compte_ses_echecs(staff):
    """I3 : pas de force brute illimitée avant la première connexion."""
    from jeflink.common.ratelimit import client as redis_client

    totp = enroll(staff)
    TotpDevice.objects.update(confirmed_at=None)
    for n in range(10):
        login(Client(), "000000", ip=f"10.6.0.{n}")
    assert TotpDevice.objects.get().locked_at is not None
    redis_client().flushdb()
    assert login(Client(), code_for(totp), ip="10.6.1.1").status_code == 200


def test_appareil_non_confirme_expire_apres_24_h(staff):
    from datetime import timedelta

    totp = enroll(staff)
    TotpDevice.objects.update(confirmed_at=None, created_at=timezone.now() - timedelta(hours=25))
    assert login(Client(), code_for(totp)).status_code == 200
    assert TotpDevice.objects.get().confirmed_at is None


def test_cle_de_session_change_a_la_connexion(staff):
    """M1 : le passage au second facteur change l'identifiant de session."""
    totp = enroll(staff)
    client = Client()
    client.force_login(staff)
    before = client.session.session_key
    assert login(client, code_for(totp)).status_code == 302
    assert client.session.session_key != before
    assert client.get(reverse("admin:index")).status_code == 200


def test_enrolement_refuse_un_compte_ops(admins, monkeypatch):
    """M2 : l'invariant staff ≠ ops est défendu par la commande."""
    from django.core.management.base import OutputWrapper

    monkeypatch.setattr(OutputWrapper, "isatty", lambda self: True)
    target = User.objects.create_superuser("+221770000098", PASSWORD)
    from jeflink.accounts.models import RoleGrant

    RoleGrant.objects.create(user=target, role=Role.OPS, reason_code="t")
    with pytest.raises(CommandError):
        enroll_cmd(admins, target)


def test_audits_de_connexion(staff):
    """M4 : mot de passe faux tracé (identifiant pseudonymisé), confirmation distincte."""
    from jeflink.common.pii import phone_hmac

    login(Client(), "000000", password="faux")
    failed = AuditEvent.objects.get(action="accounts.admin.login_failed")
    assert failed.metadata == {"username_hmac": phone_hmac(PHONE)}
    totp = enroll(staff)
    TotpDevice.objects.update(confirmed_at=None)
    login(Client(), code_for(totp))
    assert AuditEvent.objects.filter(action="accounts.admin.totp_confirmed").count() == 1
    assert AuditEvent.objects.get(action="accounts.admin.logged_in").actor_kind == "user"


def test_code_admin_filtre_des_journaux():
    """M6 : la clé otp_code est masquée."""
    from jeflink.common.pii import redact

    assert "482913" not in redact("POST otp_code=482913&username=x")
