"""Second facteur TOTP des Ops (spec 001, parcours Ops ; S1, S25 ; tâche 13).

- Après un OTP réussi sur la console, un compte ops ne reçoit pas de session : un
  ``MfaChallenge`` (jeton de 32 octets, haché, 5 min, 5 essais) mène à ``verify``, ou à
  l'enrôlement (``setup`` puis ``confirm``) qui exige un **jeton d'enrôlement** remis hors bande.
- Le secret TOTP n'existe qu'en MultiFernet (``MFA_ENCRYPTION_KEYS``). Un code déjà utilisé
  (même pas de temps ou antérieur) est refusé : ``last_used_step``.
- 10 échecs sur 24 h verrouillent le TOTP et révoquent les sessions console jusqu'à
  ``reset_ops_mfa`` (deux Admin). Le verrou est compté en base, sous verrou de ligne : il tient
  sans Redis.
"""

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

import pyotp
from cryptography.fernet import Fernet, MultiFernet
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from jeflink.common.alerts import alert_once
from jeflink.common.errors import DomainError
from jeflink.trust.models import AuditEvent
from jeflink.trust.services import audit

from .models import (
    DeviceSession,
    MfaChallenge,
    OpsEnrollmentToken,
    OtpChallenge,
    Role,
    TotpDevice,
    User,
)
from .selectors import has_role
from .sessions import TokenPair, account_allowed, create_session, issue_access, revoke_all_sessions

TOTP_INTERVAL = 30
TOTP_DIGITS = 6
VALID_WINDOW = 1  # ±30 s de dérive d'horloge du téléphone
MFA_TOKEN_TTL = timedelta(minutes=5)
MAX_TOKEN_ATTEMPTS = 5
ENROLLMENT_TTL = timedelta(hours=24)
FAILURES_BEFORE_LOCK = 10
FAILURE_WINDOW = timedelta(hours=24)
# Préfixes de jetons aléatoires (repérables par gitleaks et par le filtre de logs), pas des secrets.
MFA_TOKEN_PREFIX = "jfm_"  # noqa: S105
ENROLLMENT_PREFIX = "jfe_"


@dataclass(frozen=True)
class MfaStart:
    """Réponse de ``otp/verify`` pour un Ops sur la console : pas de session, un jeton MFA."""

    mfa_token: str
    enrollment_required: bool
    user: User


@dataclass(frozen=True)
class MfaResult:
    user: User
    tokens: TokenPair


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _fernet() -> MultiFernet:
    return MultiFernet([Fernet(key) for key in settings.MFA_ENCRYPTION_KEYS])


def _totp(device: TotpDevice) -> pyotp.TOTP:
    secret = _fernet().decrypt(device.secret_encrypted.encode()).decode()
    return pyotp.TOTP(secret, digits=TOTP_DIGITS, interval=TOTP_INTERVAL)


def _matched_step(device: TotpDevice, code: str, now: datetime) -> int | None:
    """Pas de temps du code s'il est valable (fenêtre ±1), comparé sans sortie anticipée."""
    totp = _totp(device)
    current = totp.timecode(now)
    matched = None
    for step in range(current - VALID_WINDOW, current + VALID_WINDOW + 1):
        if hmac.compare_digest(totp.generate_otp(step), code):
            matched = step
    return matched


def _accept_code(device: TotpDevice, code: str, now: datetime) -> bool:
    """Code valable et jamais utilisé (anti-rejeu). Met à jour ``last_used_step``."""
    step = _matched_step(device, code, now)
    if step is None or step <= device.last_used_step:
        return False
    device.last_used_step = step
    return True


# --- Jeton d'enrôlement (S1) --------------------------------------------------------------------


def issue_enrollment_token(*, user: User, operator: str) -> str:
    """Émet un jeton d'enrôlement (24 h, usage unique) et invalide les précédents.

    Appelé par ``grant_ops_role`` et ``reset_ops_mfa`` : le jeton en clair n'est affiché qu'une
    fois, à l'équipe technique, qui le remet hors bande. Jamais stocké en clair.
    """
    now = timezone.now()
    OpsEnrollmentToken.objects.filter(user=user, used_at__isnull=True, expires_at__gt=now).update(
        expires_at=now
    )
    token = ENROLLMENT_PREFIX + secrets.token_urlsafe(32)
    OpsEnrollmentToken.objects.create(
        user=user,
        token_hash=hash_token(token),
        issued_by_operator=operator,
        expires_at=now + ENROLLMENT_TTL,
    )
    return token


# --- Challenge MFA -------------------------------------------------------------------------------


def open_mfa_challenge(
    *, user: User, otp_challenge: OtpChallenge, device_label: str, install_id: str
) -> MfaStart:
    """Après l'OTP d'un compte ops sur la console : jeton MFA à usage unique, 5 min."""
    token = MFA_TOKEN_PREFIX + secrets.token_urlsafe(32)
    MfaChallenge.objects.create(
        user=user,
        otp_challenge=otp_challenge,
        token_hash=hash_token(token),
        app=DeviceSession.App.CONSOLE,
        device_label=device_label,
        install_id=install_id,
        expires_at=timezone.now() + MFA_TOKEN_TTL,
    )
    enrolled = TotpDevice.objects.filter(user=user, confirmed_at__isnull=False).exists()
    return MfaStart(mfa_token=token, enrollment_required=not enrolled, user=user)


def reissue_mfa_challenge(*, otp_challenge: OtpChallenge) -> MfaStart | None:
    """Rejeu de ``otp/verify`` (T1) sur le parcours Ops : nouveau jeton pour le challenge MFA
    encore vivant du même OTP ; l'ancien jeton cesse de valoir. None s'il n'y en a pas."""
    with transaction.atomic():
        challenge = (
            MfaChallenge.objects.select_for_update(of=("self",))
            .select_related("user")
            .filter(
                otp_challenge=otp_challenge,
                used_at__isnull=True,
                expires_at__gt=timezone.now(),
                failed_attempts__lt=MAX_TOKEN_ATTEMPTS,
            )
            .order_by("-created_at")
            .first()
        )
        if challenge is None:
            return None
        token = MFA_TOKEN_PREFIX + secrets.token_urlsafe(32)
        challenge.token_hash = hash_token(token)
        challenge.save(update_fields=["token_hash", "updated_at"])
    enrolled = TotpDevice.objects.filter(user=challenge.user, confirmed_at__isnull=False).exists()
    return MfaStart(mfa_token=token, enrollment_required=not enrolled, user=challenge.user)


def _locked_challenge(mfa_token: str, now: datetime) -> MfaChallenge:
    """Challenge MFA vivant, verrouillé. Sinon ``mfa_token_invalid`` (même réponse partout)."""
    challenge = (
        MfaChallenge.objects.select_for_update(of=("self",))
        .select_related("user")
        .filter(token_hash=hash_token(mfa_token or ""))
        .first()
    )
    if (
        challenge is None
        or challenge.used_at is not None
        or challenge.expires_at <= now
        or challenge.failed_attempts >= MAX_TOKEN_ATTEMPTS
        or not account_allowed(challenge.user)
        or not has_role(challenge.user, Role.OPS)
    ):
        raise DomainError("mfa_token_invalid", status=401)
    return challenge


def _locked_device(user: User) -> TotpDevice | None:
    return TotpDevice.objects.select_for_update().filter(user=user).first()


def _open_console_session(challenge: MfaChallenge, now: datetime) -> TokenPair:
    challenge.used_at = now
    challenge.save(update_fields=["used_at", "updated_at"])
    return create_session(
        user=challenge.user,
        app=DeviceSession.App.CONSOLE,
        platform=DeviceSession.Platform.WEB,
        device_label=challenge.device_label,
        install_id=challenge.install_id,
        mfa_verified_at=now,
    )


# --- Échecs et verrou ----------------------------------------------------------------------------


def _record_failure(*, challenge_id: int | None, user: User, count_device: bool) -> int:
    """Compte un échec (jeton MFA, et TOTP du compte si confirmé). Renvoie les essais restants.

    Transaction propre : l'échec survit à l'erreur levée ensuite. Au 10e échec sur 24 h, le TOTP
    est verrouillé et les sessions console révoquées.
    """
    remaining = 0
    locked = False
    with transaction.atomic():
        now = timezone.now()
        if challenge_id is not None:
            challenge = MfaChallenge.objects.select_for_update().get(pk=challenge_id)
            challenge.failed_attempts += 1
            challenge.save(update_fields=["failed_attempts", "updated_at"])
            remaining = max(0, MAX_TOKEN_ATTEMPTS - challenge.failed_attempts)
        device = _locked_device(user) if count_device else None
        if device is not None and device.confirmed_at is not None and device.locked_at is None:
            if device.failure_window_start is None or now - device.failure_window_start > (
                FAILURE_WINDOW
            ):
                device.failure_window_start = now
                device.failure_count = 0
            device.failure_count += 1
            if device.failure_count >= FAILURES_BEFORE_LOCK:
                device.locked_at = now
                locked = True
            device.save(
                update_fields=["failure_window_start", "failure_count", "locked_at", "updated_at"]
            )
            if locked:
                revoke_all_sessions(
                    user=user, reason=DeviceSession.RevokedReason.MFA_LOCKED, app="console"
                )
    audit(
        action="accounts.mfa.failed",
        actor_kind=AuditEvent.ActorKind.SYSTEM,
        target=user,
        metadata={"locked": locked},
        durable=True,
    )
    if locked:
        audit(
            action="accounts.mfa.locked",
            actor_kind=AuditEvent.ActorKind.SYSTEM,
            target=user,
            metadata={},
            durable=True,
        )
        alert_once(f"mfa_locked:{user.public_id}", 3600, "mfa_locked")
        remaining = 0
    return remaining


# --- Enrôlement ----------------------------------------------------------------------------------


def setup_totp(*, mfa_token: str, enrollment_token: str) -> dict[str, str]:
    """Nouvelle clé TOTP (non confirmée) contre un jeton d'enrôlement valide (S1).

    Refusé si un TOTP confirmé existe déjà : un changement passe par ``reset_ops_mfa``.
    """
    with transaction.atomic():
        now = timezone.now()
        challenge = _locked_challenge(mfa_token, now)
        user = challenge.user
        device = _locked_device(user)
        enrollment = (
            OpsEnrollmentToken.objects.select_for_update()
            .filter(
                user=user,
                token_hash=hash_token(enrollment_token or ""),
                used_at__isnull=True,
                expires_at__gt=now,
            )
            .first()
        )
        allowed = enrollment is not None and (device is None or device.confirmed_at is None)
        if allowed:
            secret = pyotp.random_base32(length=32)
            encrypted = _fernet().encrypt(secret.encode()).decode()
            if device is None:
                device = TotpDevice(user=user)
            device.secret_encrypted = encrypted
            device.confirmed_at = None
            device.last_used_step = 0
            device.locked_at = None
            device.failure_count = 0
            device.failure_window_start = None
            device.save()
            challenge.enrollment_token = enrollment
            challenge.save(update_fields=["enrollment_token", "updated_at"])
            uri = pyotp.TOTP(secret, digits=TOTP_DIGITS, interval=TOTP_INTERVAL).provisioning_uri(
                name=user.display_name or "Ops", issuer_name="Jeflink"
            )
            return {"secret": secret, "otpauth_uri": uri}
    _record_failure(challenge_id=challenge.pk, user=user, count_device=False)
    raise DomainError("mfa_enrollment_not_authorized", status=403)


def confirm_totp(*, mfa_token: str, code: str) -> MfaResult:
    """Premier code de l'application d'authentification : TOTP confirmé, session console ouverte."""
    with transaction.atomic():
        now = timezone.now()
        challenge = _locked_challenge(mfa_token, now)
        user = challenge.user
        device = _locked_device(user)
        enrollment = (
            OpsEnrollmentToken.objects.select_for_update()
            .filter(pk=challenge.enrollment_token_id, used_at__isnull=True, expires_at__gt=now)
            .first()
        )
        if device is None or device.confirmed_at is not None or enrollment is None:
            raise DomainError("mfa_enrollment_not_authorized", status=403)
        if _accept_code(device, code, now):
            device.confirmed_at = now
            device.save(update_fields=["confirmed_at", "last_used_step", "updated_at"])
            enrollment.used_at = now
            enrollment.save(update_fields=["used_at", "updated_at"])
            tokens = _open_console_session(challenge, now)
            audit(
                action="accounts.mfa.enrolled",
                actor=user,
                actor_kind=AuditEvent.ActorKind.USER,
                target=user,
                session_public_id=tokens.session.public_id,
                metadata={},
            )
            return MfaResult(user=user, tokens=tokens)
    remaining = _record_failure(challenge_id=challenge.pk, user=user, count_device=False)
    raise DomainError("mfa_invalid", attempts_remaining=remaining)


# --- Vérification et step-up --------------------------------------------------------------------


def verify_totp(*, mfa_token: str, code: str) -> MfaResult:
    with transaction.atomic():
        now = timezone.now()
        challenge = _locked_challenge(mfa_token, now)
        user = challenge.user
        device = _locked_device(user)
        if device is None or device.confirmed_at is None:
            raise DomainError("mfa_token_invalid", status=401)
        if device.locked_at is not None:
            raise DomainError("mfa_locked", status=403)
        if _accept_code(device, code, now):
            device.save(update_fields=["last_used_step", "updated_at"])
            return MfaResult(user=user, tokens=_open_console_session(challenge, now))
    remaining = _record_failure(challenge_id=challenge.pk, user=user, count_device=True)
    if remaining == 0 and TotpDevice.objects.filter(user=user, locked_at__isnull=False).exists():
        raise DomainError("mfa_locked", status=403)
    raise DomainError("mfa_invalid", attempts_remaining=remaining)


def step_up(*, user: User, session_public_id, code: str) -> tuple[str, datetime]:
    """TOTP de moins de 5 min pour les actions ``manage`` (S25) : access neuf, ``mfa_at`` à jour."""
    with transaction.atomic():
        now = timezone.now()
        session = (
            DeviceSession.objects.select_for_update()
            .select_related("user")
            .filter(
                public_id=session_public_id,
                user=user,
                policy="console_ops",
                revoked_at__isnull=True,
                idle_expires_at__gt=now,
                absolute_expires_at__gt=now,
            )
            .first()
        )
        if session is None or not has_role(user, Role.OPS):
            raise DomainError("ops_forbidden", status=403)
        device = _locked_device(user)
        if device is None or device.confirmed_at is None or device.locked_at is not None:
            raise DomainError("mfa_locked", status=403)
        if _accept_code(device, code, now):
            device.save(update_fields=["last_used_step", "updated_at"])
            session.mfa_verified_at = now
            session.save(update_fields=["mfa_verified_at", "updated_at"])
            return issue_access(session, now)
    _record_failure(challenge_id=None, user=user, count_device=True)
    if TotpDevice.objects.filter(user=user, locked_at__isnull=False).exists():
        raise DomainError("mfa_locked", status=403)
    raise DomainError("mfa_invalid")


# --- Réinitialisation (commande reset_ops_mfa) --------------------------------------------------


@transaction.atomic
def reset_totp(*, user: User, operator: str, second_operator: str, reason_code: str) -> str:
    """Supprime le TOTP, invalide les challenges MFA et les sessions console, émet un jeton
    d'enrôlement. Renvoie le jeton en clair, à remettre hors bande."""
    user = User.objects.select_for_update(no_key=True).get(pk=user.pk)
    TotpDevice.objects.filter(user=user).delete()
    now = timezone.now()
    MfaChallenge.objects.filter(user=user, used_at__isnull=True).update(used_at=now)
    revoke_all_sessions(user=user, reason=DeviceSession.RevokedReason.MFA_RESET, app="console")
    token = issue_enrollment_token(user=user, operator=operator)
    audit(
        action="accounts.mfa.reset",
        actor_kind=AuditEvent.ActorKind.OPS,
        target=user,
        metadata={
            "operator": operator,
            "second_operator": second_operator,
            "reason_code": reason_code,
        },
    )
    return token
