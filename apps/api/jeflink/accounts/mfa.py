"""Second facteur TOTP des Ops (spec 001, parcours Ops ; S1, S25 ; tâche 13).

- Après un OTP réussi sur la console, un compte ops ne reçoit pas de session : un
  ``MfaChallenge`` (jeton de 32 octets, haché, 5 min, 5 essais) mène à ``verify``, ou à
  l'enrôlement (``setup`` puis ``confirm``) qui exige un **jeton d'enrôlement** remis hors bande.
- Le secret TOTP n'existe qu'en MultiFernet (``MFA_ENCRYPTION_KEYS``). Un code déjà utilisé
  (même pas de temps ou antérieur) est refusé : ``last_used_step``.
- 10 échecs sur 24 h glissantes verrouillent le TOTP et révoquent les sessions console jusqu'à
  ``reset_ops_mfa`` (deux Admin). Compté en base : il tient sans Redis.

Concurrence (revue sécurité tâche 13, C1, I1, I3) :
- **un seul ordre de verrous** dans tout le module et dans ``reset_totp`` : compte (``User``),
  puis ``TotpDevice``, puis ``MfaChallenge``, puis sessions. Le verrou du compte sérialise
  toutes les tentatives d'un même Ops ;
- le code est testé **et** l'échec compté dans la même transaction, qui est validée ; l'erreur
  n'est levée qu'après. Une rafale de requêtes parallèles voit donc chaque échec précédent.
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
# Libellé neutre dans l'application d'authentification : aucune donnée personnelle (M5).
OTPAUTH_LABEL = "Console"
# Préfixes de jetons aléatoires (repérables par gitleaks et par le filtre de logs), pas des secrets.
MFA_TOKEN_PREFIX = "jfm_"  # noqa: S105
ENROLLMENT_PREFIX = "jfe_"


class Stage:
    SETUP = "setup"
    CONFIRM = "confirm"
    VERIFY = "verify"
    STEP_UP = "step_up"
    ADMIN = "admin"


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


@dataclass(frozen=True)
class _Failure:
    """Échec déjà compté et validé en base, à auditer puis à lever hors transaction."""

    user: User
    stage: str
    code: str
    status: int
    attempts_remaining: int | None
    locked: bool


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


# --- Verrous (ordre unique : compte → TOTP → challenge → sessions) ------------------------------


def _lock_user(user_id: int) -> User:
    return User.objects.select_for_update(no_key=True).get(pk=user_id)


def _lock_device(user: User) -> TotpDevice | None:
    return TotpDevice.objects.select_for_update().filter(user=user).first()


def _challenge_owner(mfa_token: str) -> int:
    """Compte du challenge, lu **sans verrou** pour prendre d'abord le verrou du compte."""
    user_id = (
        MfaChallenge.objects.filter(token_hash=hash_token(mfa_token or ""))
        .values_list("user_id", flat=True)
        .first()
    )
    if user_id is None:
        raise DomainError("mfa_token_invalid", status=401)
    return user_id


def _lock_live_challenge(mfa_token: str, user: User, now: datetime) -> MfaChallenge:
    """Challenge MFA vivant du compte, verrouillé. Sinon ``mfa_token_invalid`` (même réponse)."""
    challenge = (
        MfaChallenge.objects.select_for_update()
        .filter(token_hash=hash_token(mfa_token or ""), user=user)
        .first()
    )
    if (
        challenge is None
        or challenge.used_at is not None
        or challenge.expires_at <= now
        or challenge.failed_attempts >= MAX_TOKEN_ATTEMPTS
        or not account_allowed(user)
        or not has_role(user, Role.OPS)
    ):
        raise DomainError("mfa_token_invalid", status=401)
    challenge.user = user
    return challenge


# --- Échecs --------------------------------------------------------------------------------------


def _recent_failures(device: TotpDevice, now: datetime) -> list[float]:
    horizon = (now - FAILURE_WINDOW).timestamp()
    return [t for t in device.recent_failures if t > horizon]


def _count_failure(
    *,
    user: User,
    stage: str,
    now: datetime,
    challenge: MfaChallenge | None,
    device: TotpDevice | None,
    code: str = "mfa_invalid",
    count_unconfirmed: bool = False,
) -> _Failure:
    """Compte l'échec **sous les verrous déjà pris** (même transaction que le test du code).

    Jeton : un essai de moins. TOTP confirmé : échec daté, fenêtre glissante de 24 h ; au 10e,
    verrou et révocation des sessions console.
    """
    remaining = None
    if challenge is not None:
        challenge.failed_attempts += 1
        challenge.save(update_fields=["failed_attempts", "updated_at"])
        remaining = MAX_TOKEN_ATTEMPTS - challenge.failed_attempts
    locked = False
    counted = device is not None and (device.confirmed_at is not None or count_unconfirmed)
    if counted and device.locked_at is None:
        device.recent_failures = [*_recent_failures(device, now), now.timestamp()]
        if len(device.recent_failures) >= FAILURES_BEFORE_LOCK:
            device.locked_at = now
            locked = True
        device.save(update_fields=["recent_failures", "locked_at", "updated_at"])
        if locked:
            revoke_all_sessions(
                user=user, reason=DeviceSession.RevokedReason.MFA_LOCKED, app="console"
            )
    if locked:
        return _Failure(user, stage, "mfa_locked", 403, 0, True)
    return _Failure(user, stage, code, 400 if code == "mfa_invalid" else 403, remaining, False)


def _raise(failure: _Failure) -> None:
    """Hors transaction : audit durable de l'échec (et du verrou), puis l'erreur."""
    audit(
        action="accounts.mfa.failed",
        actor_kind=AuditEvent.ActorKind.SYSTEM,
        target=failure.user,
        metadata={"stage": failure.stage, "locked": failure.locked},
        durable=True,
    )
    if failure.locked:
        audit(
            action="accounts.mfa.locked",
            actor_kind=AuditEvent.ActorKind.SYSTEM,
            target=failure.user,
            metadata={},
            durable=True,
        )
        alert_once(f"mfa_locked:{failure.user.public_id}", 3600, "mfa_locked")
    extra = {}
    if failure.code == "mfa_invalid" and failure.attempts_remaining is not None:
        extra["attempts_remaining"] = max(0, failure.attempts_remaining)
    raise DomainError(failure.code, status=failure.status, **extra)


# --- Jeton d'enrôlement (S1) --------------------------------------------------------------------


def issue_enrollment_token(*, user: User, operator: str) -> str:
    """Émet un jeton d'enrôlement (24 h, usage unique) et invalide les précédents. Audité.

    Appelé par ``grant_ops_role`` et ``reset_ops_mfa`` : le jeton en clair n'est remis qu'une
    fois à l'équipe technique, qui le transmet hors bande. Jamais stocké en clair.
    """
    now = timezone.now()
    OpsEnrollmentToken.objects.filter(user=user, used_at__isnull=True, expires_at__gt=now).update(
        expires_at=now
    )
    token = ENROLLMENT_PREFIX + secrets.token_urlsafe(32)
    OpsEnrollmentToken.objects.create(
        user=user,
        token_hash=hash_token(token),
        issued_by_operator=operator[:64],
        expires_at=now + ENROLLMENT_TTL,
    )
    audit(
        action="accounts.mfa.enrollment_issued",
        actor_kind=AuditEvent.ActorKind.OPS,
        target=user,
        metadata={"operator": operator[:64]},
    )
    return token


# --- Challenge MFA -------------------------------------------------------------------------------


def _is_enrolled(user: User) -> bool:
    return TotpDevice.objects.filter(user=user, confirmed_at__isnull=False).exists()


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
    return MfaStart(mfa_token=token, enrollment_required=not _is_enrolled(user), user=user)


def reissue_mfa_challenge(*, otp_challenge: OtpChallenge) -> MfaStart | None:
    """Rejeu de ``otp/verify`` (T1) sur le parcours Ops : nouveau jeton pour le challenge MFA
    encore vivant du même OTP ; l'ancien jeton cesse de valoir. None s'il n'y en a pas."""
    if otp_challenge.user_id is None:
        return None
    with transaction.atomic():
        user = _lock_user(otp_challenge.user_id)
        challenge = (
            MfaChallenge.objects.select_for_update()
            .filter(
                otp_challenge=otp_challenge,
                user=user,
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
    return MfaStart(mfa_token=token, enrollment_required=not _is_enrolled(user), user=user)


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


def _audit_success(action: str, user: User, session: DeviceSession) -> None:
    audit(
        action=action,
        actor=user,
        actor_kind=AuditEvent.ActorKind.USER,
        target=user,
        session_public_id=session.public_id,
        metadata={},
    )


# --- Enrôlement ----------------------------------------------------------------------------------


def setup_totp(*, mfa_token: str, enrollment_token: str) -> dict[str, str]:
    """Nouvelle clé TOTP (non confirmée) contre un jeton d'enrôlement valide (S1).

    Refusé si un TOTP confirmé existe déjà : un changement passe par ``reset_ops_mfa``.
    """
    user_id = _challenge_owner(mfa_token)
    with transaction.atomic():
        now = timezone.now()
        user = _lock_user(user_id)
        device = _lock_device(user)
        challenge = _lock_live_challenge(mfa_token, user, now)
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
        if enrollment is None or (device is not None and device.confirmed_at is not None):
            failure = _count_failure(
                user=user,
                stage=Stage.SETUP,
                now=now,
                challenge=challenge,
                device=None,
                code="mfa_enrollment_not_authorized",
            )
        else:
            secret = pyotp.random_base32(length=32)
            if device is None:
                device = TotpDevice(user=user)
            device.secret_encrypted = _fernet().encrypt(secret.encode()).decode()
            device.confirmed_at = None
            device.last_used_step = 0
            device.locked_at = None
            device.recent_failures = []
            device.save()
            challenge.enrollment_token = enrollment
            challenge.save(update_fields=["enrollment_token", "updated_at"])
            uri = pyotp.TOTP(secret, digits=TOTP_DIGITS, interval=TOTP_INTERVAL).provisioning_uri(
                name=OTPAUTH_LABEL, issuer_name="Jeflink"
            )
            return {"secret": secret, "otpauth_uri": uri}
    _raise(failure)


def confirm_totp(*, mfa_token: str, code: str) -> MfaResult:
    """Premier code de l'application d'authentification : TOTP confirmé, session console ouverte."""
    user_id = _challenge_owner(mfa_token)
    with transaction.atomic():
        now = timezone.now()
        user = _lock_user(user_id)
        device = _lock_device(user)
        challenge = _lock_live_challenge(mfa_token, user, now)
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
            _audit_success("accounts.mfa.enrolled", user, tokens.session)
            return MfaResult(user=user, tokens=tokens)
        failure = _count_failure(
            user=user, stage=Stage.CONFIRM, now=now, challenge=challenge, device=None
        )
    _raise(failure)


# --- Vérification et step-up --------------------------------------------------------------------


def verify_totp(*, mfa_token: str, code: str) -> MfaResult:
    user_id = _challenge_owner(mfa_token)
    with transaction.atomic():
        now = timezone.now()
        user = _lock_user(user_id)
        device = _lock_device(user)
        challenge = _lock_live_challenge(mfa_token, user, now)
        if device is None or device.confirmed_at is None:
            raise DomainError("mfa_token_invalid", status=401)
        if device.locked_at is not None:
            raise DomainError("mfa_locked", status=403)
        if _accept_code(device, code, now):
            device.save(update_fields=["last_used_step", "updated_at"])
            tokens = _open_console_session(challenge, now)
            _audit_success("accounts.mfa.verified", user, tokens.session)
            return MfaResult(user=user, tokens=tokens)
        failure = _count_failure(
            user=user, stage=Stage.VERIFY, now=now, challenge=challenge, device=device
        )
    _raise(failure)


def step_up(*, user: User, session_public_id, code: str) -> tuple[str, datetime]:
    """TOTP de moins de 5 min pour les actions ``manage`` (S25) : access neuf, ``mfa_at`` à jour."""
    with transaction.atomic():
        now = timezone.now()
        user = _lock_user(user.pk)
        device = _lock_device(user)
        session = (
            DeviceSession.objects.select_for_update(of=("self",))
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
        if device is None or device.confirmed_at is None or device.locked_at is not None:
            raise DomainError("mfa_locked", status=403)
        if _accept_code(device, code, now):
            device.save(update_fields=["last_used_step", "updated_at"])
            session.mfa_verified_at = now
            session.save(update_fields=["mfa_verified_at", "updated_at"])
            _audit_success("accounts.mfa.step_up", user, session)
            return issue_access(session, now)
        failure = _count_failure(
            user=user, stage=Stage.STEP_UP, now=now, challenge=None, device=device
        )
    _raise(failure)


# --- Réinitialisation et retrait -----------------------------------------------------------------


def clear_mfa(user: User) -> None:
    """Supprime le TOTP, expire les jetons d'enrôlement et les challenges MFA vivants, révoque
    les sessions console. À appeler dans une transaction qui tient déjà le verrou du compte."""
    now = timezone.now()
    TotpDevice.objects.filter(user=user).delete()
    OpsEnrollmentToken.objects.filter(user=user, used_at__isnull=True, expires_at__gt=now).update(
        expires_at=now
    )
    MfaChallenge.objects.filter(user=user, used_at__isnull=True).update(used_at=now)
    revoke_all_sessions(user=user, reason=DeviceSession.RevokedReason.MFA_RESET, app="console")


@transaction.atomic
def reset_totp(*, user: User, operator: str, second_operator: str, reason_code: str) -> str:
    """``reset_ops_mfa`` : efface le second facteur et émet un nouveau jeton d'enrôlement.
    Renvoie le jeton en clair, à remettre hors bande."""
    user = _lock_user(user.pk)
    clear_mfa(user)
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
