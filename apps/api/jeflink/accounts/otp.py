"""Connexion par code SMS (spec 001, « OTP » ; S8, S11, S12, S16 ; T1).

- ``request_otp`` : réserve le budget SMS **avant** toute écriture, crée toujours un nouveau
  challenge et un secret de 32 octets (stocké haché). Même ``Idempotency-Key`` (même app, même
  appareil) avant la fin du délai de renvoi : même corps, aucun SMS (T1). La réponse ne dépend
  jamais de l'existence du compte (anti-énumération).
- ``verify_otp`` : ordre des contrôles fixé et testé — format, challenge, code, compte,
  création. Chaque échec est validé en base avant la réponse ; le succès (validation du
  challenge, compte, session) est atomique et la validation touche exactement une ligne.
- Un numéro bloqué (10 échecs sur 24 h) ne peut plus rien vérifier ni renvoyer (I1).
- Le code est généré dans le worker (``tasks.send_otp``) et n'existe qu'en HMAC.
"""

import base64
import contextlib
import hashlib
import hmac
import json
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import redis
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from jeflink.common.errors import DomainError
from jeflink.common.pii import phone_hmac
from jeflink.common.ratelimit import (
    Limit,
    RateLimitUnavailable,
    client,
    consume,
    incr_counter,
    pseudonymize,
)
from jeflink.trust.models import AuditEvent
from jeflink.trust.services import audit

from .client_challenge import check_client_challenge
from .models import DeviceSession, NoticeSms, OtpChallenge, OtpDelivery, Role, User
from .otp_limits import (
    FallbackCounts,
    phone_blocked_until,
    record_verified,
    record_verify_failure,
    resend_delay,
    reserve_sms,
)
from .phone import normalize_phone, phone_display, phone_region
from .selectors import active_sessions_for, has_role
from .sessions import (
    TokenPair,
    clean_install_id,
    create_session,
    is_dormant_login,
    reissue_session,
)

CODE_LENGTH = 6
CHALLENGE_TTL = timedelta(minutes=30)
CODE_TTL = timedelta(minutes=10)
MAX_DELIVERIES = 3
MAX_ATTEMPTS = 5
REPLAY_WINDOW = timedelta(minutes=2)
MAX_REPLAYS = 3
IN_FLIGHT_TTL = 30
# Même exigence que l'install_id : au moins 128 bits aléatoires côté app (UUID v4).
_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9_-]{22,64}$")


# --- Hachage ------------------------------------------------------------------------------


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def hash_code(delivery_public_id, code: str) -> str:
    """HMAC du code, lié à son envoi : un code ne vaut que pour la livraison qui l'a porté."""
    key = settings.OTP_HMAC_KEY.encode()
    return hmac.new(key, f"{delivery_public_id}:{code}".encode(), hashlib.sha256).hexdigest()


def new_code() -> str:
    return f"{secrets.randbelow(10**CODE_LENGTH):0{CODE_LENGTH}d}"


# --- Repli en base (Redis indisponible) -------------------------------------------------------


def db_counts(phone: str, region: str) -> FallbackCounts:
    """SMS réellement tentés, comptés en base (S8) : codes et SMS d'information."""
    now = timezone.now()
    hour_ago = now - timedelta(hours=1)
    day = OtpDelivery.objects.filter(created_at__gte=now - timedelta(hours=24))
    notices = NoticeSms.objects.filter(created_at__gte=now - timedelta(hours=24))
    own_notices = notices.filter(phone_hmac=phone_hmac(phone))
    return FallbackCounts(
        phone_last_hour=day.filter(challenge__phone=phone, created_at__gte=hour_ago).count()
        + own_notices.filter(created_at__gte=hour_ago).count(),
        phone_last_day=day.filter(challenge__phone=phone).count() + own_notices.count(),
        total_last_day=day.count() + notices.count(),
        region_last_day=day.filter(challenge__region=region).count()
        + notices.filter(region=region).count(),
    )


# --- Idempotence de la demande (T1) -----------------------------------------------------------
# Redis seulement (pas de champ en base) : si Redis tombe, la limite par IP refuse de toute
# façon la demande (spec 001, « Limites de débit »).


def _idempotency_cache_key(idempotency_key: str, phone: str, app: str, install_id: str) -> str:
    return f"jf:otp:idem:{pseudonymize(f'{idempotency_key}|{phone}|{app}|{install_id}')}"


def _fernet() -> Fernet:
    # Clé dédiée dérivée d'OTP_HMAC_KEY : la réponse gardée contient le challenge_secret.
    digest = hashlib.sha256(b"jeflink-otp-idempotency|" + settings.OTP_HMAC_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _remember_response(cache_key: str, body: dict, ttl: int) -> None:
    token = _fernet().encrypt(json.dumps(body).encode())
    with contextlib.suppress(redis.RedisError):
        client().set(cache_key, token, ex=max(ttl, 1))


def _recall_response(cache_key: str) -> dict | None:
    try:
        token = client().get(cache_key)
    except redis.RedisError:
        return None
    if not token:
        return None
    try:
        return json.loads(_fernet().decrypt(token))
    except (InvalidToken, ValueError):
        return None


def _claim_in_flight(cache_key: str) -> bool:
    """Verrou court : deux demandes simultanées avec la même clé ne créent qu'un challenge (M2)."""
    try:
        return bool(client().set(f"{cache_key}:lock", 1, nx=True, ex=IN_FLIGHT_TTL))
    except redis.RedisError:
        return True  # sans Redis, la limite par IP refuse déjà la demande


def _release_in_flight(cache_key: str) -> None:
    with contextlib.suppress(redis.RedisError):
        client().delete(f"{cache_key}:lock")


# --- Demande et renvoi ----------------------------------------------------------------------


def _count_refused_region(region: str) -> None:
    """Demandes hors région comptées par région et par heure, jamais le numéro (T3, M11)."""
    with contextlib.suppress(RateLimitUnavailable):
        incr_counter("metrics:otp_region_refused", region or "??", 3600)


def _response_body(
    challenge: OtpChallenge, deliveries: int, resend_at: datetime, secret: str | None
) -> dict:
    body = {
        "challenge_id": str(challenge.public_id),
        "phone_display": phone_display(challenge.phone),
        "code_length": CODE_LENGTH,
        "expires_at": challenge.expires_at.isoformat(),
        "resend_available_at": resend_at.isoformat(),
        "deliveries_remaining": MAX_DELIVERIES - deliveries,
    }
    if secret is not None:
        body["challenge_secret"] = secret
    return body


def _enqueue(delivery: OtpDelivery) -> None:
    from .tasks import send_otp

    delivery_id = str(delivery.public_id)
    transaction.on_commit(lambda: send_otp.delay(delivery_id))


def request_otp(
    *,
    raw_phone: str,
    app: str,
    idempotency_key: str,
    install_id: str = "",
    language: str = "fr",
    client_challenge_token: str = "",
) -> dict:
    """Crée un challenge de connexion et programme le premier SMS. Renvoie le corps ``202``."""
    if not _IDEMPOTENCY_KEY.match(idempotency_key or ""):
        raise DomainError("idempotency_key_required")
    phone = normalize_phone(raw_phone)
    region = phone_region(phone)
    if region not in settings.OTP_ALLOWED_REGIONS:
        _count_refused_region(region)
        raise DomainError("phone_region_not_supported")
    install_id = clean_install_id(install_id)

    # Le rappel d'idempotence n'envoie rien : il passe avant le défi client (M10).
    cache_key = _idempotency_cache_key(idempotency_key, phone, app, install_id)
    remembered = _recall_response(cache_key)
    if remembered is not None:
        return remembered
    check_client_challenge(token=client_challenge_token, app=app)
    if not _claim_in_flight(cache_key):
        raise DomainError("otp_request_in_progress", status=409)
    try:
        # Budget SMS réservé avant toute écriture : un refus ne crée rien.
        reserve_sms(
            phone=phone,
            region=region,
            install_id=install_id,
            new_challenge=True,
            fallback=db_counts,
        )
        now = timezone.now()
        secret = secrets.token_urlsafe(32)
        with transaction.atomic():
            challenge = OtpChallenge.objects.create(
                phone=phone,
                region=region,
                purpose=OtpChallenge.Purpose.LOGIN,
                challenge_secret_hash=hash_secret(secret),
                app=app,
                language=language if language in {"fr", "wo"} else "fr",
                expires_at=now + CHALLENGE_TTL,
            )
            delivery = OtpDelivery.objects.create(challenge=challenge, attempt_no=1)
            _enqueue(delivery)
        resend_at = now + timedelta(seconds=resend_delay(phone))
        body = _response_body(challenge, 1, resend_at, secret)
        _remember_response(cache_key, body, int((resend_at - now).total_seconds()))
        return body
    finally:
        _release_in_flight(cache_key)


def _get_challenge(challenge_id, challenge_secret: str, *, for_update: bool) -> OtpChallenge:
    queryset = OtpChallenge.objects.select_for_update() if for_update else OtpChallenge.objects
    challenge = queryset.filter(public_id=challenge_id).first()
    presented = hash_secret(challenge_secret or "")
    stored = challenge.challenge_secret_hash if challenge else hash_secret(secrets.token_hex(8))
    # Comparaison en temps constant, même quand le challenge n'existe pas.
    if not hmac.compare_digest(presented, stored) or challenge is None:
        raise DomainError("otp_challenge_invalid")
    return challenge


def resend_otp(*, challenge_id, challenge_secret: str) -> dict:
    """Nouveau code sur le même challenge : 3 envois au plus, délai minimal entre deux.

    Pas de défi client ici : la possession du secret et le plafond de 3 envois suffisent.
    """
    with transaction.atomic():
        challenge = _get_challenge(challenge_id, challenge_secret, for_update=True)
        now = timezone.now()
        if challenge.status != OtpChallenge.Status.PENDING:
            raise DomainError("otp_challenge_invalid")
        if now >= challenge.expires_at:
            raise DomainError("otp_expired")
        blocked_until = phone_blocked_until(challenge.phone)
        if blocked_until is not None:
            wait = max(1, int((blocked_until - now).total_seconds()))
            raise DomainError("otp_rate_limited", status=429, retry_after=wait)
        deliveries = list(challenge.deliveries.order_by("attempt_no"))
        if len(deliveries) >= MAX_DELIVERIES:
            raise DomainError("otp_resend_exhausted", status=429)
        delay = timedelta(seconds=resend_delay(challenge.phone))
        available = deliveries[-1].created_at + delay
        if now < available:
            wait = max(1, int((available - now).total_seconds()))
            raise DomainError("otp_resend_too_early", status=429, retry_after=wait)
        reserve_sms(
            phone=challenge.phone,
            region=challenge.region,
            new_challenge=False,
            fallback=db_counts,
        )
        delivery = OtpDelivery.objects.create(challenge=challenge, attempt_no=len(deliveries) + 1)
        _enqueue(delivery)
    return _response_body(challenge, len(deliveries) + 1, now + delay, secret=None)


# --- Vérification ---------------------------------------------------------------------------


@dataclass
class VerifyResult:
    user: User
    tokens: TokenPair
    is_new_user: bool
    restricted: bool
    other_sessions: list[DeviceSession] = field(default_factory=list)


def _code_matches(challenge: OtpChallenge, code: str, *, now: datetime | None) -> bool:
    """Compare à **tous** les codes (non expirés si ``now``), sans sortie anticipée."""
    matched = False
    for delivery in challenge.deliveries.exclude(code_hash=""):
        if now is not None and (delivery.expires_at is None or delivery.expires_at <= now):
            continue
        matched |= hmac.compare_digest(hash_code(delivery.public_id, code), delivery.code_hash)
    return matched


def _register_failure(challenge: OtpChallenge) -> None:
    """Échec validé en base avant la réponse ; au 5e, le challenge est verrouillé (S8)."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE accounts_otpchallenge
            SET failed_attempts = failed_attempts + 1,
                status = CASE WHEN failed_attempts + 1 >= %s THEN 'locked' ELSE status END,
                updated_at = NOW()
            WHERE id = %s AND status = 'pending' AND failed_attempts < %s
            RETURNING failed_attempts, status
            """,
            [MAX_ATTEMPTS, challenge.pk, MAX_ATTEMPTS],
        )
        row = cursor.fetchone()
    if row is None:
        # Verrouillé ou validé entre-temps : aucun échec supplémentaire compté pour le numéro.
        raise DomainError("otp_locked", status=429)
    record_verify_failure(challenge.phone)
    attempts, status = row
    if status == OtpChallenge.Status.LOCKED:
        audit(
            action="accounts.otp.locked",
            metadata={"phone_hmac": phone_hmac(challenge.phone), "app": challenge.app},
            durable=True,
        )
        raise DomainError("otp_locked", status=429)
    raise DomainError("otp_invalid", attempts_remaining=MAX_ATTEMPTS - attempts)


def verify_otp(
    *,
    challenge_id,
    challenge_secret: str,
    code: str,
    terms_version: str,
    app: str,
    platform: str,
    device_label: str = "",
    install_id: str = "",
) -> VerifyResult:
    # 1. Format et conditions : identiques que le compte existe ou non (S11).
    if terms_version != settings.TERMS_VERSION:
        raise DomainError("terms_not_accepted")
    # 2. Challenge.
    challenge = _get_challenge(challenge_id, challenge_secret, for_update=False)
    if challenge.purpose != OtpChallenge.Purpose.LOGIN or challenge.app != app:
        raise DomainError("otp_challenge_invalid")
    now = timezone.now()
    if challenge.status == OtpChallenge.Status.VERIFIED:
        return _replay(challenge, code=code, install_id=install_id, now=now)
    if challenge.status == OtpChallenge.Status.LOCKED or phone_blocked_until(challenge.phone):
        raise DomainError("otp_locked", status=429)
    if challenge.status == OtpChallenge.Status.EXPIRED or now >= challenge.expires_at:
        OtpChallenge.objects.filter(pk=challenge.pk, status=OtpChallenge.Status.PENDING).update(
            status=OtpChallenge.Status.EXPIRED
        )
        raise DomainError("otp_expired")
    # 3. Code. « Expiré » seulement si un code a réellement expiré : un envoi échoué (code
    # effacé) répond comme un mauvais code, sans révéler la joignabilité du numéro (M7).
    delivered = challenge.deliveries.exclude(code_hash="")
    if delivered.exists() and not delivered.filter(expires_at__gt=now).exists():
        raise DomainError("otp_expired")
    if not _code_matches(challenge, code, now=now):
        _register_failure(challenge)
    # 4. État du compte : un refus consomme le challenge et laisse une trace (M12).
    user = User.objects.filter(phone=challenge.phone, deleted_at__isnull=True).first()
    refusal = _refusal_reason(user, app)
    if refusal is not None:
        _consume_refused(challenge, refusal, now=now, install_id=install_id)
    # 5. Validation, création éventuelle et session : tout ou rien (M5).
    result = _open_session(
        challenge,
        user=user,
        app=app,
        platform=platform,
        device_label=device_label,
        install_id=install_id,
        now=now,
    )
    record_verified(challenge.phone)
    return result


def _refusal_reason(user: User | None, app: str) -> tuple[str, str, int] | None:
    """(code d'erreur, motif d'audit, statut HTTP) si le compte ne peut pas se connecter."""
    if user is None:
        return None
    if not user.is_active:
        return ("account_disabled", "disabled", 403)
    if user.is_staff or user.is_superuser:
        return ("account_not_allowed", "technical_account", 403)
    if user.is_review_account:
        return ("account_not_allowed", "review_account", 403)
    if app == DeviceSession.App.CONSOLE and has_role(user, Role.OPS):
        # Second facteur obligatoire pour les Ops : branché à la tâche 13.
        return ("ops_mfa_unavailable", "ops_mfa_unavailable", 403)
    return None


def _consume_refused(
    challenge: OtpChallenge, refusal: tuple[str, str, int], *, now: datetime, install_id: str
) -> None:
    code, reason, status = refusal
    OtpChallenge.objects.filter(pk=challenge.pk, status=OtpChallenge.Status.PENDING).update(
        status=OtpChallenge.Status.VERIFIED,
        verified_at=now,
        verified_install_id=clean_install_id(install_id),
    )
    audit(
        action="accounts.otp.login_refused",
        metadata={"reason": reason, "app": challenge.app},
        durable=True,
    )
    raise DomainError(code, status=status)


def _open_session(
    challenge: OtpChallenge,
    *,
    user: User | None,
    app: str,
    platform: str,
    device_label: str,
    install_id: str,
    now: datetime,
) -> VerifyResult:
    with transaction.atomic():
        # Exactement une ligne passe de « pending » à « verified » ; une requête concurrente
        # attend ce verrou puis ne trouve plus rien à valider.
        updated = OtpChallenge.objects.filter(
            pk=challenge.pk, status=OtpChallenge.Status.PENDING
        ).update(
            status=OtpChallenge.Status.VERIFIED,
            verified_at=now,
            verified_install_id=clean_install_id(install_id),
        )
        if updated != 1:
            raise DomainError("otp_already_used", status=409)
        is_new = user is None
        if is_new:
            try:
                with transaction.atomic():
                    user = User.objects.create_user(challenge.phone)
            except IntegrityError:
                # Deux premières connexions simultanées sur le même numéro.
                user = User.objects.get(phone=challenge.phone, deleted_at__isnull=True)
                is_new = False
        if user.terms_version != settings.TERMS_VERSION or user.phone_verified_at is None:
            user.terms_version = settings.TERMS_VERSION
            user.terms_accepted_at = now
            user.phone_verified_at = user.phone_verified_at or now
            user.save(
                update_fields=[
                    "terms_version",
                    "terms_accepted_at",
                    "phone_verified_at",
                    "updated_at",
                ]
            )
        if is_new:
            audit(action="accounts.user.created", actor=user, target=user, metadata={"app": app})
        restricted = not is_new and is_dormant_login(user=user, install_id=install_id)
        tokens = create_session(
            user=user,
            app=app,
            platform=platform,
            device_label=device_label,
            install_id=install_id,
            restricted=restricted,
        )
        # « Vous êtes aussi connecté sur… » (T2), calculé après la création (M6) ;
        # jamais montré à une session restreinte.
        others = (
            []
            if tokens.session.restricted
            else list(active_sessions_for(user).exclude(pk=tokens.session.pk)[:10])
        )
        OtpChallenge.objects.filter(pk=challenge.pk).update(session=tokens.session, user=user)
        audit(
            action="accounts.otp.verified",
            actor=user,
            actor_kind=AuditEvent.ActorKind.USER,
            target=user,
            session_public_id=tokens.session.public_id,
            metadata={
                "app": app,
                "is_new_user": is_new,
                "restricted": tokens.session.restricted,
                "replay": False,
            },
        )
    return VerifyResult(
        user=user,
        tokens=tokens,
        is_new_user=is_new,
        restricted=tokens.session.restricted,
        other_sessions=others,
    )


def _replay(challenge: OtpChallenge, *, code: str, install_id: str, now: datetime) -> VerifyResult:
    """Rejeu dans les 2 min (T1) : même code valable, même secret, même appareil → même session.

    3 rejeux au plus par challenge ; chaque réémission est auditée (M4).
    """
    install_id = clean_install_id(install_id)
    eligible = (
        challenge.verified_at is not None
        and now - challenge.verified_at <= REPLAY_WINDOW
        and install_id
        and hmac.compare_digest(install_id, challenge.verified_install_id)
        and challenge.session_id is not None
        and _code_matches(challenge, code, now=now)
    )
    if not eligible:
        raise DomainError("otp_already_used", status=409)
    replay_limit = Limit("otp:replay", MAX_REPLAYS, int(REPLAY_WINDOW.total_seconds()))
    try:
        allowed = consume([(replay_limit, str(challenge.public_id))]).allowed
    except RateLimitUnavailable:
        allowed = False
    if not allowed:
        raise DomainError("otp_already_used", status=409)
    session = DeviceSession.objects.select_related("user").get(pk=challenge.session_id)
    tokens = reissue_session(session)
    audit(
        action="accounts.otp.verified",
        actor=session.user,
        actor_kind=AuditEvent.ActorKind.USER,
        target=session.user,
        session_public_id=session.public_id,
        metadata={
            "app": challenge.app,
            "is_new_user": False,
            "restricted": session.restricted,
            "replay": True,
        },
    )
    return VerifyResult(
        user=session.user,
        tokens=tokens,
        is_new_user=False,
        restricted=session.restricted,
    )
