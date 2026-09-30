"""Connexion par code SMS (spec 001, « OTP » ; S8, S11, S12, S16 ; T1).

- ``request_otp`` : réserve le budget SMS **avant** toute écriture, crée toujours un nouveau
  challenge et un secret de 32 octets (stocké haché). Même ``Idempotency-Key`` avant la fin du
  délai de renvoi : même corps, aucun SMS (T1). La réponse ne dépend jamais de l'existence du
  compte (anti-énumération).
- ``verify_otp`` : ordre des contrôles fixé et testé — format, challenge, code, compte,
  création. Chaque échec est validé en base avant la réponse ; la validation passe par un
  UPDATE conditionnel qui touche exactement une ligne.
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
from jeflink.common.ratelimit import Limit, client, consume, pseudonymize
from jeflink.trust.models import AuditEvent
from jeflink.trust.services import audit

from .client_challenge import check_client_challenge
from .models import DeviceSession, OtpChallenge, OtpDelivery, Role, User
from .otp_limits import (
    FallbackCounts,
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
_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


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
    """SMS réellement tentés, comptés en base (S8)."""
    now = timezone.now()
    day = OtpDelivery.objects.filter(created_at__gte=now - timedelta(hours=24))
    return FallbackCounts(
        phone_last_hour=day.filter(
            challenge__phone=phone, created_at__gte=now - timedelta(hours=1)
        ).count(),
        phone_last_day=day.filter(challenge__phone=phone).count(),
        total_last_day=day.count(),
        region_last_day=day.filter(challenge__region=region).count(),
    )


# --- Idempotence de la demande (T1) -----------------------------------------------------------


def _idempotency_cache_key(idempotency_key: str, phone: str) -> str:
    return f"jf:otp:idem:{pseudonymize(f'{idempotency_key}|{phone}')}"


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


# --- Demande et renvoi ----------------------------------------------------------------------


def _count_refused_region(region: str) -> None:
    """On compte les demandes hors région, par région, sans jamais garder le numéro (T3)."""
    with contextlib.suppress(Exception):
        consume([(Limit("metrics:otp_region_refused_24h", 10**9, 86400), region or "??")])


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
    check_client_challenge(token=client_challenge_token, app=app)

    cache_key = _idempotency_cache_key(idempotency_key, phone)
    remembered = _recall_response(cache_key)
    if remembered is not None:
        return remembered

    # Budget SMS réservé avant toute écriture : un refus ne crée rien.
    reserve_sms(
        phone=phone,
        region=region,
        install_id=clean_install_id(install_id),
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
    """Nouveau code sur le même challenge : 3 envois au plus, délai minimal entre deux."""
    with transaction.atomic():
        challenge = _get_challenge(challenge_id, challenge_secret, for_update=True)
        now = timezone.now()
        if challenge.status != OtpChallenge.Status.PENDING:
            raise DomainError("otp_challenge_invalid")
        if now >= challenge.expires_at:
            raise DomainError("otp_expired")
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
    record_verify_failure(challenge.phone)
    if row is None:
        # Verrouillé ou validé entre-temps par une requête concurrente.
        raise DomainError("otp_locked", status=429)
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
    if challenge.status == OtpChallenge.Status.LOCKED:
        raise DomainError("otp_locked", status=429)
    if challenge.status == OtpChallenge.Status.EXPIRED or now >= challenge.expires_at:
        OtpChallenge.objects.filter(pk=challenge.pk, status=OtpChallenge.Status.PENDING).update(
            status=OtpChallenge.Status.EXPIRED
        )
        raise DomainError("otp_expired")
    # 3. Code.
    live = challenge.deliveries.exclude(code_hash="").filter(expires_at__gt=now)
    if not live.exists():
        raise DomainError("otp_expired")
    if not _code_matches(challenge, code, now=now):
        _register_failure(challenge)
    # Validation : exactement une ligne passe de « pending » à « verified ».
    updated = OtpChallenge.objects.filter(
        pk=challenge.pk, status=OtpChallenge.Status.PENDING
    ).update(
        status=OtpChallenge.Status.VERIFIED,
        verified_at=now,
        verified_install_id=clean_install_id(install_id),
    )
    if updated != 1:
        raise DomainError("otp_already_used", status=409)
    record_verified(challenge.phone)
    # 4. État du compte, puis 5. création éventuelle et session.
    return _open_session(
        challenge,
        app=app,
        platform=platform,
        device_label=device_label,
        install_id=install_id,
        now=now,
    )


def _open_session(
    challenge: OtpChallenge,
    *,
    app: str,
    platform: str,
    device_label: str,
    install_id: str,
    now: datetime,
) -> VerifyResult:
    user = User.objects.filter(phone=challenge.phone, deleted_at__isnull=True).first()
    if user is not None:
        if not user.is_active:
            raise DomainError("account_disabled", status=403)
        if user.is_staff or user.is_superuser or user.is_review_account:
            raise DomainError("account_not_allowed", status=403)
        if app == DeviceSession.App.CONSOLE and has_role(user, Role.OPS):
            # Second facteur obligatoire pour les Ops : branché à la tâche 13.
            raise DomainError("ops_mfa_unavailable", status=403)

    is_new = user is None
    with transaction.atomic():
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
        # « Vous êtes aussi connecté sur… » (T2) ; jamais montré à une session restreinte.
        others = [] if restricted else list(active_sessions_for(user)[:10])
        tokens = create_session(
            user=user,
            app=app,
            platform=platform,
            device_label=device_label,
            install_id=install_id,
            restricted=restricted,
        )
        OtpChallenge.objects.filter(pk=challenge.pk).update(session=tokens.session, user=user)
        audit(
            action="accounts.otp.verified",
            actor=user,
            actor_kind=AuditEvent.ActorKind.USER,
            target=user,
            session_public_id=tokens.session.public_id,
            metadata={"app": app, "is_new_user": is_new, "restricted": tokens.session.restricted},
        )
    return VerifyResult(
        user=user,
        tokens=tokens,
        is_new_user=is_new,
        restricted=tokens.session.restricted,
        other_sessions=others,
    )


def _replay(challenge: OtpChallenge, *, code: str, install_id: str, now: datetime) -> VerifyResult:
    """Rejeu dans les 2 min (T1) : même code, même secret, même appareil → même session."""
    install_id = clean_install_id(install_id)
    eligible = (
        challenge.verified_at is not None
        and now - challenge.verified_at <= REPLAY_WINDOW
        and install_id
        and hmac.compare_digest(install_id, challenge.verified_install_id)
        and challenge.session_id is not None
        and _code_matches(challenge, code, now=None)
    )
    if not eligible:
        raise DomainError("otp_already_used", status=409)
    session = DeviceSession.objects.select_related("user").get(pk=challenge.session_id)
    tokens = reissue_session(session)
    return VerifyResult(
        user=session.user,
        tokens=tokens,
        is_new_user=False,
        restricted=session.restricted,
    )
