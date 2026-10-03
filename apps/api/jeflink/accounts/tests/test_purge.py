"""Tâche 18 : purge quotidienne des données d'authentification."""

import uuid
from datetime import timedelta

import pytest
from django.conf import settings
from django.utils import timezone

from jeflink.accounts import purge
from jeflink.accounts.models import (
    DeviceSession,
    MfaChallenge,
    NoticeSms,
    OpsEnrollmentToken,
    OtpChallenge,
    OtpDelivery,
    OtpPhoneBlock,
    PhoneChangeRequest,
    RetiredRefreshToken,
    RoleInvitation,
)
from jeflink.accounts.sessions import create_session, refresh_session, revoke_session
from jeflink.accounts.tasks import purge_auth_data
from jeflink.common.pii import phone_hmac

pytestmark = pytest.mark.django_db

PHONE = "+221771234567"


def ago(**kwargs):
    return timezone.now() - timedelta(**kwargs)


def backdate(obj, **fields):
    type(obj).objects.filter(pk=obj.pk).update(**fields)


def challenge(**kwargs):
    defaults = {
        "phone": PHONE,
        "region": "SN",
        "purpose": "login",
        "challenge_secret_hash": "x",
        "app": "client",
        "expires_at": timezone.now() + timedelta(minutes=30),
    }
    return OtpChallenge.objects.create(**{**defaults, **kwargs})


def invitation(owner, **kwargs):
    defaults = {
        "phone": PHONE,
        "phone_hmac": phone_hmac(PHONE),
        "role": "technician",
        "invited_by": owner,
        "context_ref": uuid.uuid4(),
        "expires_at": timezone.now() + timedelta(days=7),
    }
    return RoleInvitation.objects.create(**{**defaults, **kwargs})


# --- Clôture -------------------------------------------------------------------------------------


def test_invitation_expiree_close_et_numero_efface(user_factory):
    owner = user_factory()
    old = invitation(owner, expires_at=ago(minutes=1))
    live = invitation(owner, phone="+221781234567", context_ref=uuid.uuid4())
    purge.close_expired()
    old.refresh_from_db()
    live.refresh_from_db()
    assert (old.status, old.phone) == ("expired", "")
    assert (live.status, live.phone) == ("pending", "+221781234567")


def test_demande_de_changement_expiree_close(user_factory):
    user, ops = user_factory(), user_factory()
    code = challenge(purpose="change_phone", user=user, phone="+221781234567")
    request = PhoneChangeRequest.objects.create(
        user=user,
        new_phone="+221781234567",
        new_phone_hmac="h",
        requested_by=ops,
        requires_approval=False,
        reason_code="number_changed",
        status="approved",
        challenge=code,
        expires_at=ago(minutes=1),
    )
    purge.close_expired()
    request.refresh_from_db()
    code.refresh_from_db()
    assert (request.status, request.new_phone) == ("expired", "")
    assert code.status == "expired"  # le code en cours ne vaut plus


def test_sms_d_information_bloque_ferme(user_factory):
    stuck = NoticeSms.objects.create(kind="invitation", phone=PHONE, phone_hmac="h", region="SN")
    fresh = NoticeSms.objects.create(kind="invitation", phone=PHONE, phone_hmac="h", region="SN")
    backdate(stuck, created_at=ago(hours=2))
    purge.close_expired()
    stuck.refresh_from_db()
    fresh.refresh_from_db()
    assert (stuck.status, stuck.phone, stuck.error_code) == ("unknown", "", "stuck")
    assert (fresh.status, fresh.phone) == ("queued", PHONE)


# --- Suppression ----------------------------------------------------------------------------------


def test_challenges_otp_et_envois_apres_7_jours():
    old, recent = challenge(), challenge()
    OtpDelivery.objects.create(challenge=old, attempt_no=1)
    backdate(old, created_at=ago(days=8))
    purge.delete_expired()
    assert list(OtpChallenge.objects.all()) == [recent]
    assert not OtpDelivery.objects.exists()


def test_sessions_revoquees_ou_expirees_apres_90_jours(user_factory):
    user = user_factory()
    revoked = create_session(user=user, app="client", platform="android")
    refresh_session(revoked.refresh)  # crée un refresh retiré
    revoke_session(revoked.session, reason="logout")
    backdate(revoked.session, revoked_at=ago(days=91))
    expired = create_session(user=user, app="web", platform="web")
    backdate(expired.session, idle_expires_at=ago(days=91))
    active = create_session(user=user, app="pro", platform="android")
    recent_revoked = create_session(user=user, app="console", platform="web")
    revoke_session(recent_revoked.session, reason="logout")

    purge.delete_expired()
    remaining = set(DeviceSession.objects.values_list("pk", flat=True))
    assert remaining == {active.session.pk, recent_revoked.session.pk}
    assert not RetiredRefreshToken.objects.filter(session_id=revoked.session.pk).exists()


def test_demandes_closes_apres_30_jours(user_factory):
    owner = user_factory()
    closed = invitation(owner, status="declined", phone="")
    recent_closed = invitation(owner, status="accepted", phone="", context_ref=uuid.uuid4())
    pending = invitation(owner, context_ref=uuid.uuid4())
    backdate(closed, updated_at=ago(days=31))
    backdate(pending, updated_at=ago(days=31))
    purge.delete_expired()
    assert set(RoleInvitation.objects.values_list("pk", flat=True)) == {
        recent_closed.pk,
        pending.pk,
    }


def test_blocage_otp_24_h_apres_echeance():
    old = OtpPhoneBlock.objects.create(phone_hmac="a" * 64, level=1, blocked_until=ago(hours=25))
    recent = OtpPhoneBlock.objects.create(phone_hmac="b" * 64, level=1, blocked_until=ago(hours=2))
    purge.delete_expired()
    assert list(OtpPhoneBlock.objects.all()) == [recent]
    assert old.pk not in OtpPhoneBlock.objects.values_list("pk", flat=True)


def test_jetons_mfa_expires(user_factory):
    user = user_factory()
    otp = challenge(app="console")
    old = MfaChallenge.objects.create(
        user=user, otp_challenge=otp, token_hash="a" * 64, app="console", expires_at=ago(days=8)
    )
    live = MfaChallenge.objects.create(
        user=user,
        otp_challenge=otp,
        token_hash="b" * 64,
        app="console",
        expires_at=timezone.now() + timedelta(minutes=5),
    )
    OpsEnrollmentToken.objects.create(
        user=user, token_hash="c" * 64, issued_by_operator="zay", expires_at=ago(days=8)
    )
    purge.delete_expired()
    assert list(MfaChallenge.objects.all()) == [live]
    assert old.pk not in MfaChallenge.objects.values_list("pk", flat=True)
    assert not OpsEnrollmentToken.objects.exists()


# --- Exécution -----------------------------------------------------------------------------------


def test_par_lots_et_relancable(monkeypatch):
    monkeypatch.setattr(purge, "BATCH", 2)
    for _ in range(5):
        backdate(challenge(), created_at=ago(days=8))
    assert purge.delete_expired().counts["otp_challenges"] == 5
    assert purge.delete_expired().counts["otp_challenges"] == 0


def test_tache_planifiee_et_sans_donnee_personnelle(user_factory, caplog):
    owner = user_factory()
    invitation(owner, expires_at=ago(minutes=1))
    schedule = settings.CELERY_BEAT_SCHEDULE["accounts-purge-auth-data"]
    assert schedule["task"] == "jeflink.accounts.tasks.purge_auth_data"
    with caplog.at_level("INFO"):
        counts = purge_auth_data.delay().get()
    assert counts["invitations_expired"] == 1
    assert PHONE not in caplog.text and "771234567" not in caplog.text
