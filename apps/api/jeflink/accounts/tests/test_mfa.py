"""Tâche 13 : second facteur TOTP des Ops (S1, S25)."""

from datetime import timedelta
from io import StringIO

import pytest
from django.contrib.auth.models import Group
from django.core.management import CommandError, call_command
from django.urls import reverse
from django.utils import timezone
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from jeflink.accounts.mfa import (
    MAX_TOKEN_ATTEMPTS,
    confirm_totp,
    issue_enrollment_token,
    open_mfa_challenge,
    reset_totp,
    setup_totp,
    step_up,
    verify_totp,
)
from jeflink.accounts.models import (
    DeviceSession,
    MfaChallenge,
    OpsEnrollmentToken,
    OtpChallenge,
    Role,
    TotpDevice,
)
from jeflink.accounts.permissions import HasOpsPerm
from jeflink.accounts.services import grant_role, revoke_role
from jeflink.accounts.sessions import create_session
from jeflink.accounts.tokens import decode_access
from jeflink.common.errors import DomainError
from jeflink.trust.models import AuditEvent

from .mfa_helpers import enroll


@pytest.fixture(autouse=True)
def terminal(monkeypatch):
    """Les commandes écrivent dans un StringIO : on simule un terminal (jeton affichable)."""
    from django.core.management.base import OutputWrapper

    monkeypatch.setattr(OutputWrapper, "isatty", lambda self: True)


# Les échecs sont audités hors transaction (connexion « audit ») : tests transactionnels.
pytestmark = pytest.mark.django_db(transaction=True, databases="__all__", serialized_rollback=True)


@pytest.fixture
def ops(user_factory):
    user = user_factory(display_name="Aïda")
    grant_role(user=user, role=Role.OPS, reason_code="t", operator="a", second_operator="b")
    user.groups.add(Group.objects.get(name="Admin"))
    return user


def start(user) -> str:
    """Jeton MFA, comme après un OTP réussi sur la console."""
    otp = OtpChallenge.objects.create(
        phone=user.phone,
        region="SN",
        purpose=OtpChallenge.Purpose.LOGIN,
        challenge_secret_hash="x",
        app="console",
        status=OtpChallenge.Status.VERIFIED,
        expires_at=timezone.now() + timedelta(minutes=30),
    )
    return open_mfa_challenge(
        user=user, otp_challenge=otp, device_label="Chrome", install_id=""
    ).mfa_token


def code_for(totp, *, offset=0) -> str:
    return totp.at(timezone.now() + timedelta(seconds=30 * offset))


def raises(expected, fn, **kwargs):
    with pytest.raises(DomainError) as exc:
        fn(**kwargs)
    assert exc.value.code == expected
    return exc.value


# --- Enrôlement (S1) -----------------------------------------------------------------------------


def test_enrolement_complet(ops):
    import pyotp

    enrollment = issue_enrollment_token(user=ops, operator="zay")
    token = start(ops)
    body = setup_totp(mfa_token=token, enrollment_token=enrollment)
    assert body["otpauth_uri"].startswith("otpauth://totp/Jeflink:")
    assert ops.phone[1:] not in body["otpauth_uri"]  # jamais le numéro dans l'URI
    device = TotpDevice.objects.get(user=ops)
    assert body["secret"] not in device.secret_encrypted  # secret chiffré (MultiFernet)
    assert device.confirmed_at is None

    result = confirm_totp(mfa_token=token, code=pyotp.TOTP(body["secret"]).now())
    session = result.tokens.session
    assert (session.app, session.policy) == ("console", "console_ops")
    claims = decode_access(result.tokens.access)
    assert claims["mfa"] is True
    device.refresh_from_db()
    assert device.confirmed_at is not None
    assert OpsEnrollmentToken.objects.get().used_at is not None
    assert AuditEvent.objects.filter(action="accounts.mfa.enrolled").count() == 1
    # Jeton MFA à usage unique.
    raises("mfa_token_invalid", confirm_totp, mfa_token=token, code="000000")


def test_setup_sans_jeton_d_enrolement_valide(ops, user_factory):
    token = start(ops)
    raises("mfa_enrollment_not_authorized", setup_totp, mfa_token=token, enrollment_token="x")
    # Jeton d'un autre compte, expiré ou déjà utilisé : même refus.
    other = user_factory()
    foreign = issue_enrollment_token(user=other, operator="zay")
    raises("mfa_enrollment_not_authorized", setup_totp, mfa_token=token, enrollment_token=foreign)
    expired = issue_enrollment_token(user=ops, operator="zay")
    OpsEnrollmentToken.objects.filter(user=ops).update(expires_at=timezone.now())
    raises("mfa_enrollment_not_authorized", setup_totp, mfa_token=token, enrollment_token=expired)
    assert not TotpDevice.objects.exists()
    assert MfaChallenge.objects.get().failed_attempts == 3


def test_setup_refuse_si_un_totp_est_deja_confirme(ops):
    enroll(ops)
    enrollment = issue_enrollment_token(user=ops, operator="zay")
    raises(
        "mfa_enrollment_not_authorized",
        setup_totp,
        mfa_token=start(ops),
        enrollment_token=enrollment,
    )


def test_nouveau_jeton_d_enrolement_invalide_le_precedent(ops):
    first = issue_enrollment_token(user=ops, operator="zay")
    issue_enrollment_token(user=ops, operator="zay")
    raises(
        "mfa_enrollment_not_authorized", setup_totp, mfa_token=start(ops), enrollment_token=first
    )


def test_confirm_code_faux(ops):
    enrollment = issue_enrollment_token(user=ops, operator="zay")
    token = start(ops)
    setup_totp(mfa_token=token, enrollment_token=enrollment)
    error = raises("mfa_invalid", confirm_totp, mfa_token=token, code="000000")
    assert error.extra["attempts_remaining"] == MAX_TOKEN_ATTEMPTS - 1
    assert TotpDevice.objects.get().confirmed_at is None


# --- Vérification --------------------------------------------------------------------------------


def test_verification(ops):
    totp = enroll(ops)
    result = verify_totp(mfa_token=start(ops), code=code_for(totp))
    assert decode_access(result.tokens.access)["mfa"] is True
    assert MfaChallenge.objects.get().used_at is not None


def test_code_rejoue_refuse(ops):
    """Anti-rejeu : un code déjà utilisé ne rouvre pas de session, même avec un autre jeton."""
    totp = enroll(ops)
    code = code_for(totp)
    verify_totp(mfa_token=start(ops), code=code)
    raises("mfa_invalid", verify_totp, mfa_token=start(ops), code=code)
    # Le code du pas suivant reste accepté (fenêtre ±30 s).
    verify_totp(mfa_token=start(ops), code=code_for(totp, offset=1))


def test_cinq_essais_par_jeton(ops):
    enroll(ops)
    token = start(ops)
    for _ in range(MAX_TOKEN_ATTEMPTS):
        raises("mfa_invalid", verify_totp, mfa_token=token, code="000000")
    raises("mfa_token_invalid", verify_totp, mfa_token=token, code="000000")


def test_dix_echecs_verrouillent_la_console(ops):
    totp = enroll(ops)
    console = create_session(
        user=ops, app="console", platform="web", mfa_verified_at=timezone.now()
    )
    for _ in range(9):
        raises("mfa_invalid", verify_totp, mfa_token=start(ops), code="000000")
    raises("mfa_locked", verify_totp, mfa_token=start(ops), code="000000")
    assert TotpDevice.objects.get().locked_at is not None
    console.session.refresh_from_db()
    assert console.session.revoked_reason == "mfa_locked"
    assert AuditEvent.objects.filter(action="accounts.mfa.locked").count() == 1
    assert AuditEvent.objects.filter(action="accounts.mfa.failed").count() == 10
    # Même le bon code ne passe plus jusqu'à reset_ops_mfa.
    raises("mfa_locked", verify_totp, mfa_token=start(ops), code=code_for(totp))


def test_jeton_expire_ou_role_retire(ops):
    totp = enroll(ops)
    token = start(ops)
    MfaChallenge.objects.update(expires_at=timezone.now())
    raises("mfa_token_invalid", verify_totp, mfa_token=token, code=code_for(totp))
    token = start(ops)
    revoke_role(user=ops, role=Role.OPS, reason_code="departure", operator="a")
    raises("mfa_token_invalid", verify_totp, mfa_token=token, code=code_for(totp))


# --- Step-up (S25) --------------------------------------------------------------------------------


def _request(access):
    request = Request(APIRequestFactory().post("/"))
    request.auth = decode_access(access)
    return request


def test_step_up(ops):
    totp = enroll(ops)
    pair = create_session(
        user=ops,
        app="console",
        platform="web",
        mfa_verified_at=timezone.now() - timedelta(minutes=10),
    )
    manage = HasOpsPerm("ops.accounts.manage", step_up=True)()
    request = _request(pair.access)
    request.user = ops
    assert not manage.has_permission(request, None)
    assert manage.code == "ops_step_up_required"

    access, _ = step_up(user=ops, session_public_id=pair.session.public_id, code=code_for(totp))
    request = _request(access)
    request.user = ops
    assert manage.has_permission(request, None)
    claims = decode_access(access)
    assert claims["sid"] == str(pair.session.public_id)


def test_step_up_hors_console_ops(ops, user_factory):
    enroll(ops)
    client = create_session(user=ops, app="client", platform="android")
    raises("ops_forbidden", step_up, user=ops, session_public_id=client.session.public_id, code="1")


def test_step_up_code_faux_compte_pour_le_verrou(ops):
    enroll(ops)
    pair = create_session(user=ops, app="console", platform="web", mfa_verified_at=timezone.now())
    raises("mfa_invalid", step_up, user=ops, session_public_id=pair.session.public_id, code="0")
    assert len(TotpDevice.objects.get().recent_failures) == 1


def test_step_up_par_l_api(api_client, ops):
    totp = enroll(ops)
    pair = create_session(user=ops, app="console", platform="web", mfa_verified_at=timezone.now())
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {pair.access}")
    response = api_client.post(
        reverse("auth-mfa-step-up"), {"code": code_for(totp, offset=1)}, format="json"
    )
    assert response.status_code == 200
    assert set(response.json()) == {"access", "access_expires_at"}


# --- Refresh et réinitialisation -----------------------------------------------------------------


def test_refresh_recalcule_mfa(ops):
    from jeflink.accounts.sessions import refresh_session

    enroll(ops)
    pair = create_session(user=ops, app="console", platform="web", mfa_verified_at=timezone.now())
    assert decode_access(refresh_session(pair.refresh).access)["mfa"] is True
    TotpDevice.objects.update(locked_at=timezone.now())
    pair2 = create_session(user=ops, app="console", platform="web", mfa_verified_at=timezone.now())
    assert decode_access(refresh_session(pair2.refresh).access)["mfa"] is False


def test_reset(ops):
    enroll(ops)
    pair = create_session(user=ops, app="console", platform="web", mfa_verified_at=timezone.now())
    pending = start(ops)
    token = reset_totp(user=ops, operator="a", second_operator="b", reason_code="device_lost")
    assert not TotpDevice.objects.exists()
    pair.session.refresh_from_db()
    assert pair.session.revoked_reason == "mfa_reset"
    raises("mfa_token_invalid", verify_totp, mfa_token=pending, code="000000")
    # Le nouveau jeton d'enrôlement permet de réenrôler.
    body = setup_totp(mfa_token=start(ops), enrollment_token=token)
    assert body["secret"]
    event = AuditEvent.objects.get(action="accounts.mfa.reset")
    assert event.metadata["reason_code"] == "device_lost"


# --- API et parcours complet ---------------------------------------------------------------------


def test_endpoints_mfa_parcours_api(api_client, ops):
    import pyotp

    enrollment = issue_enrollment_token(user=ops, operator="zay")
    token = start(ops)
    setup = api_client.post(
        reverse("auth-mfa-setup"),
        {"mfa_token": token, "enrollment_token": enrollment},
        format="json",
    )
    assert setup.status_code == 200
    code = pyotp.TOTP(setup.json()["secret"]).now()
    response = api_client.post(
        reverse("auth-mfa-confirm"), {"mfa_token": token, "code": code}, format="json"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "authenticated"
    assert body["user"]["roles"] == ["ops"]
    assert set(body["tokens"]) == {"access", "refresh", "access_expires_at"}


def test_jeton_mfa_inconnu_401(api_client):
    response = api_client.post(
        reverse("auth-mfa-verify"), {"mfa_token": "jfm_x", "code": "123456"}, format="json"
    )
    assert response.status_code == 401
    assert response.json() == {"code": "mfa_token_invalid"}


# --- Commandes -----------------------------------------------------------------------------------


def run(name, *args):
    out = StringIO()
    call_command(name, *args, stdout=out)
    return out.getvalue()


@pytest.fixture
def admins(user_factory):
    first, second = user_factory(), user_factory()
    for admin in (first, second):
        grant_role(user=admin, role=Role.OPS, reason_code="t", operator="a", second_operator="b")
        admin.groups.add(Group.objects.get(name="Admin"))
    return first, second


def ops_args(admins, reason):
    return [
        "--operator",
        str(admins[0].public_id),
        "--second-operator",
        str(admins[1].public_id),
        "--reason",
        reason,
    ]


def test_grant_ops_role_emet_un_jeton_d_enrolement(admins, user_factory):
    target = user_factory()
    out = run(
        "grant_ops_role", "--user", str(target.public_id), "--groups", "Support",
        *ops_args(admins, "hiring"),
    )  # fmt: skip
    token = out.split("usage unique) : ")[1].strip()
    assert token.startswith("jfe_")
    assert OpsEnrollmentToken.objects.get(user=target).token_hash != token


def test_reset_ops_mfa(admins, ops):
    enroll(ops)
    out = run("reset_ops_mfa", "--user", str(ops.public_id), *ops_args(admins, "device_lost"))
    assert "jfe_" in out
    assert not TotpDevice.objects.filter(user=ops).exists()


def test_reset_ops_mfa_refuse_un_compte_non_ops(admins, user_factory):
    with pytest.raises(CommandError):
        run(
            "reset_ops_mfa", "--user", str(user_factory().public_id),
            *ops_args(admins, "device_lost"),
        )  # fmt: skip


def test_reset_ops_mfa_exige_deux_admin(admins, ops):
    with pytest.raises(CommandError):
        run(
            "reset_ops_mfa", "--user", str(ops.public_id),
            "--operator", str(admins[0].public_id),
            "--second-operator", str(admins[0].public_id),
            "--reason", "device_lost",
        )  # fmt: skip


def test_ops_sur_l_app_client_n_a_aucune_permission_ops(ops):
    enroll(ops)
    pair = create_session(user=ops, app="client", platform="android")
    request = _request(pair.access)
    request.user = ops
    assert not HasOpsPerm("ops.accounts.view", step_up=False)().has_permission(request, None)
    assert not DeviceSession.objects.filter(policy="console_ops").exists()


# --- Corrections de la revue sécurité (tâche 13) -----------------------------------------------


@pytest.mark.parametrize("stage", ["verify", "step_up"])
def test_rafale_concurrente_chaque_echec_compte(ops, stage):
    """C1, I1 : des requêtes parallèles ne testent jamais plus de codes que le budget, sans 500."""
    import threading

    from django.db import connections

    enroll(ops)
    token = start(ops)
    pair = create_session(user=ops, app="console", platform="web", mfa_verified_at=timezone.now())
    results: list[str] = []

    def attempt():
        try:
            if stage == "verify":
                verify_totp(mfa_token=token, code="000000")
            else:
                step_up(user=ops, session_public_id=pair.session.public_id, code="000000")
            results.append("ok")
        except DomainError as exc:
            results.append(exc.code)
        except Exception as exc:
            results.append(type(exc).__name__)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=attempt) for _ in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    device = TotpDevice.objects.get()
    if stage == "verify":
        assert sorted(set(results)) == ["mfa_invalid", "mfa_token_invalid"]
        assert results.count("mfa_invalid") == MAX_TOKEN_ATTEMPTS
        assert MfaChallenge.objects.get().failed_attempts == MAX_TOKEN_ATTEMPTS
        assert len(device.recent_failures) == MAX_TOKEN_ATTEMPTS
    else:
        # 9 échecs, le 10e verrouille, les suivants trouvent la session révoquée ou le verrou.
        assert results.count("mfa_invalid") == 9
        assert results.count("mfa_locked") >= 1
        assert set(results) <= {"mfa_invalid", "mfa_locked", "ops_forbidden"}
        assert device.locked_at is not None
    failed = AuditEvent.objects.filter(action="accounts.mfa.failed")
    assert failed.count() == len(device.recent_failures)
    assert {event.metadata["stage"] for event in failed} == {stage}


def test_fenetre_glissante(ops):
    """M3 : 9 échecs anciens de 23 h comptent encore ; au-delà de 24 h, ils sortent."""
    enroll(ops)
    now = timezone.now()
    TotpDevice.objects.update(recent_failures=[(now - timedelta(hours=23)).timestamp()] * 9)
    raises("mfa_locked", verify_totp, mfa_token=start(ops), code="000000")
    TotpDevice.objects.update(
        locked_at=None, recent_failures=[(now - timedelta(hours=25)).timestamp()] * 9
    )
    raises("mfa_invalid", verify_totp, mfa_token=start(ops), code="000000")
    assert len(TotpDevice.objects.get().recent_failures) == 1


def test_succes_audites_avec_la_session(ops):
    """I2 : ouverture de session console et step-up tracés, rattachés à la session."""
    totp = enroll(ops)
    result = verify_totp(mfa_token=start(ops), code=code_for(totp))
    verified = AuditEvent.objects.get(action="accounts.mfa.verified")
    assert verified.session_public_id == result.tokens.session.public_id
    step_up(
        user=ops, session_public_id=result.tokens.session.public_id, code=code_for(totp, offset=1)
    )
    event = AuditEvent.objects.get(action="accounts.mfa.step_up")
    assert event.session_public_id == result.tokens.session.public_id


def test_step_up_limite_par_ip(settings, api_client, ops):
    """I1 : le step-up déclare sa limite par IP."""
    from jeflink.accounts.api.mfa_views import TotpStepUpView

    assert TotpStepUpView.rate_limit_scope in settings.IP_RATE_LIMITS


def test_session_anterieure_a_un_reenrolement_sans_mfa(ops):
    """M7 : un facteur ré-enrôlé ne revalide pas une session d'avant son enrôlement."""
    from jeflink.accounts.sessions import refresh_session

    pair = create_session(
        user=ops,
        app="console",
        platform="web",
        mfa_verified_at=timezone.now() - timedelta(minutes=1),
    )
    enroll(ops)
    TotpDevice.objects.update(confirmed_at=timezone.now())  # ré-enrôlé après la session
    assert decode_access(refresh_session(pair.refresh).access)["mfa"] is False


def test_retrait_du_role_efface_le_second_facteur(admins, ops):
    """M1 : rendre le rôle plus tard exigera un nouvel enrôlement hors bande."""
    enroll(ops)
    issue_enrollment_token(user=ops, operator="zay")
    run("revoke_ops_role", "--user", str(ops.public_id), *ops_args(admins, "departure"))
    assert not TotpDevice.objects.filter(user=ops).exists()
    assert not OpsEnrollmentToken.objects.filter(user=ops, expires_at__gt=timezone.now()).exists()


def test_jeton_refuse_hors_terminal_sans_fichier(admins, ops, monkeypatch):
    """M2 : jamais de jeton dans les journaux d'un job."""
    from django.core.management.base import OutputWrapper

    monkeypatch.setattr(OutputWrapper, "isatty", lambda self: False)
    with pytest.raises(CommandError):
        run("reset_ops_mfa", "--user", str(ops.public_id), *ops_args(admins, "device_lost"))
    assert not AuditEvent.objects.filter(action="accounts.mfa.reset").exists()


def test_jeton_ecrit_dans_un_fichier_prive(admins, ops, monkeypatch, tmp_path):
    import os
    import stat

    from django.core.management.base import OutputWrapper

    monkeypatch.setattr(OutputWrapper, "isatty", lambda self: False)
    path = tmp_path / "jeton.txt"
    out = run(
        "reset_ops_mfa", "--user", str(ops.public_id), "--token-file", str(path),
        *ops_args(admins, "device_lost"),
    )  # fmt: skip
    token = path.read_text().strip()
    assert token.startswith("jfe_") and token not in out
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert AuditEvent.objects.filter(action="accounts.mfa.enrollment_issued").exists()
    # Jamais d'écrasement d'un fichier existant.
    with pytest.raises(CommandError):
        run(
            "reset_ops_mfa", "--user", str(ops.public_id), "--token-file", str(path),
            *ops_args(admins, "device_lost"),
        )  # fmt: skip
