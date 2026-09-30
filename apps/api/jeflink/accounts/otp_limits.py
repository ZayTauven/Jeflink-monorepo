"""Limites propres à l'OTP (spec 001, « Limites de débit » ; ADR 0008 ; S8, S12, S13).

Appelées **avant toute écriture** par ``otp/request``, ``otp/resend``, la suppression de compte,
le changement de numéro et les invitations : un SMS n'est jamais envoyé hors budget.
"""

import contextlib
import logging
from collections.abc import Callable
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from jeflink.common.errors import DomainError
from jeflink.common.pii import mask_phone, phone_hmac
from jeflink.common.ratelimit import Limit, RateLimitUnavailable, client, consume, count, reset
from jeflink.trust.services import audit

from .models import OtpPhoneBlock

alerts = logging.getLogger("jeflink.alerts")

# Repli si Redis ne répond pas : renvoie (SMS sur 1 h, SMS sur 24 h) pour ce numéro, en base.
PhoneCountFallback = Callable[[str], tuple[int, int]]

SMS_PHONE_HOUR = Limit("otp:phone_sms_1h", 5, 3600)
SMS_PHONE_DAY = Limit("otp:phone_sms_24h", 8, 86400)
REQUEST_PER_INSTALL = Limit("otp:install_request_1h", 10, 3600)
VERIFY_FAILURES = Limit("otp:phone_verify_fail_24h", 10, 86400)
BASE_RESEND_DELAY = 60
_UNLIMITED = 10**9


def operator_prefix(phone: str) -> str:
    """Préfixe opérateur à 5 chiffres (``+22177…`` → ``22177``) : jamais le numéro."""
    return phone[1:6]


def number_block(phone: str) -> str:
    """Bloc de 1 000 numéros consécutifs (pseudonymisé comme toute identité)."""
    return phone[:-3]


def _raise_rate_limited(retry_after: int) -> None:
    raise DomainError("otp_rate_limited", status=429, retry_after=retry_after)


def _raise_unavailable() -> None:
    raise DomainError("otp_temporarily_unavailable", status=503)


# --- Blocage progressif ----------------------------------------------------------------


def phone_blocked_until(phone: str):
    block = OtpPhoneBlock.objects.filter(phone_hmac=phone_hmac(phone)).first()
    if block and block.blocked_until and block.blocked_until > timezone.now():
        return block.blocked_until
    return None


def record_verify_failure(phone: str) -> bool:
    """Compte un échec de vérification ; au 10e sur 24 h glissantes, bloque le numéro.

    Renvoie True si le numéro vient d'être bloqué. Sans Redis, le plafond de 5 essais par
    challenge (en base) reste la protection.
    """
    try:
        consume([(Limit(VERIFY_FAILURES.name, _UNLIMITED, VERIFY_FAILURES.window), phone)])
        failures = count(VERIFY_FAILURES, phone)
    except RateLimitUnavailable:
        return False
    if failures < VERIFY_FAILURES.limit:
        return False
    block_phone(phone)
    with contextlib.suppress(RateLimitUnavailable):
        reset(VERIFY_FAILURES, phone)
    return True


def block_phone(phone: str) -> OtpPhoneBlock:
    """Bloque les nouveaux challenges : 1 h, puis 2 h, 4 h… jusqu'à 24 h. Audit durable."""
    now = timezone.now()
    with transaction.atomic():
        block, _ = OtpPhoneBlock.objects.select_for_update().get_or_create(
            phone_hmac=phone_hmac(phone)
        )
        # Un numéro resté tranquille plus de 24 h après son dernier blocage repart au niveau 1.
        if block.blocked_until and block.blocked_until < now - timedelta(hours=24):
            block.level = 0
        block.level += 1
        hours = min(2 ** (block.level - 1), settings.OTP_PHONE_BLOCK_MAX_HOURS)
        block.blocked_until = now + timedelta(hours=hours)
        block.save()
    audit(
        action="accounts.otp.phone_blocked",
        metadata={
            "phone_masked": mask_phone(phone),
            "phone_hmac": phone_hmac(phone),
            "level": block.level,
            "hours": hours,
        },
        durable=True,
    )
    return block


def unblock_phone(phone: str, *, actor, reason_code: str) -> bool:
    """Levée par l'Ops (``ops/accounts/{id}/unblock-otp``, tâche 15). Auditée."""
    updated = OtpPhoneBlock.objects.filter(
        phone_hmac=phone_hmac(phone), blocked_until__gt=timezone.now()
    ).update(blocked_until=timezone.now())
    if updated:
        with contextlib.suppress(RateLimitUnavailable):
            reset(VERIFY_FAILURES, phone)
        audit(
            action="ops.accounts.otp_unblocked",
            actor=actor,
            actor_kind="ops",
            metadata={"phone_hmac": phone_hmac(phone), "reason_code": reason_code},
        )
    return bool(updated)


# --- Taux de conversion (S13) -------------------------------------------------------


def _conversion_limit(kind: str) -> Limit:
    return Limit(f"otp:conv_{kind}_1h", _UNLIMITED, 3600)


def record_sms_sent(phone: str) -> None:
    with contextlib.suppress(RateLimitUnavailable):
        consume([(_conversion_limit("sent"), operator_prefix(phone))])


def record_verified(phone: str) -> None:
    with contextlib.suppress(RateLimitUnavailable):
        consume([(_conversion_limit("verified"), operator_prefix(phone))])


def is_prefix_slowed(phone: str) -> bool:
    """Moins de 20 % de codes vérifiés sur 1 h, avec un volume suffisant : pompage probable."""
    prefix = operator_prefix(phone)
    try:
        sent = count(_conversion_limit("sent"), prefix)
        verified = count(_conversion_limit("verified"), prefix)
    except RateLimitUnavailable:
        return False
    slowed = (
        sent >= settings.SMS_CONVERSION_MIN_VOLUME
        and verified / sent < settings.SMS_CONVERSION_MIN_RATE
    )
    if slowed:
        _alert_once(f"conversion:{prefix}", 3600, "sms_conversion_low", prefix=prefix)
    return slowed


def resend_delay(phone: str) -> int:
    """Délai entre deux envois d'un challenge : doublé sur un préfixe ralenti."""
    return BASE_RESEND_DELAY * (2 if is_prefix_slowed(phone) else 1)


# --- Réservation d'un SMS ----------------------------------------------------------------


def reserve_sms(
    *,
    phone: str,
    region: str,
    install_id: str = "",
    new_challenge: bool = True,
    fallback: PhoneCountFallback | None = None,
) -> None:
    """Réserve un SMS pour ``phone`` ou lève ``otp_rate_limited`` / ``otp_temporarily_unavailable``.

    Tous les plafonds sont vérifiés puis consommés ensemble : un refus ne consomme rien.
    """
    if new_challenge:
        until = phone_blocked_until(phone)
        if until is not None:
            _raise_rate_limited(max(1, int((until - timezone.now()).total_seconds())))

    slowed = is_prefix_slowed(phone)
    divisor = 2 if slowed else 1
    daily_cap = Limit("sms:daily_total", settings.SMS_DAILY_CAP, 86400)
    region_cap = Limit(
        "sms:daily_region",
        settings.SMS_DAILY_CAP_BY_REGION.get(region, settings.SMS_DAILY_CAP),
        86400,
    )
    checks = [
        (SMS_PHONE_HOUR, phone),
        (SMS_PHONE_DAY, phone),
        (Limit("sms:prefix_1h", settings.SMS_PREFIX_HOURLY_CAP // divisor, 3600),
         operator_prefix(phone)),
        (Limit("sms:block_1h", settings.SMS_BLOCK_HOURLY_CAP // divisor, 3600),
         number_block(phone)),
        (daily_cap, "all"),
        (region_cap, region),
    ]  # fmt: skip
    if install_id and new_challenge:
        checks.append((REQUEST_PER_INSTALL, install_id))

    try:
        outcome = consume(checks)
    except RateLimitUnavailable:
        _reserve_with_fallback(phone, fallback)
        return

    if not outcome.allowed:
        if outcome.exceeded.startswith("sms:daily"):
            _cap_reached(outcome.exceeded, region)
            _raise_unavailable()
        _raise_rate_limited(outcome.retry_after)
    _check_daily_thresholds(daily_cap)


def _reserve_with_fallback(phone: str, fallback: PhoneCountFallback | None) -> None:
    """Redis indisponible : comptage en base des SMS du numéro, sinon refus (jamais ouvert)."""
    if fallback is None:
        _raise_unavailable()
    last_hour, last_day = fallback(phone)
    if last_hour >= SMS_PHONE_HOUR.limit or last_day >= SMS_PHONE_DAY.limit:
        _raise_rate_limited(SMS_PHONE_HOUR.window)
    alerts.warning("ratelimit_redis_unavailable fallback=db")


def _cap_reached(name: str, region: str) -> None:
    if _alert_once(f"cap:{name}:{region}", 3600, "sms_cap_reached", cap=name, region=region):
        audit(
            action="system.sms_cap.reached",
            metadata={"cap": name, "region": region},
            durable=True,
        )


def _check_daily_thresholds(daily_cap: Limit) -> None:
    try:
        used = count(daily_cap, "all")
    except RateLimitUnavailable:
        return
    for threshold in (80, 50):
        if used * 100 >= daily_cap.limit * threshold:
            _alert_once(f"daily:{threshold}", 86400, "sms_daily_threshold", percent=threshold)
            return


def _alert_once(key: str, ttl: int, code: str, **fields: object) -> bool:
    """Émet une alerte au plus une fois par période. Renvoie True si elle vient d'être émise."""
    try:
        first = client().set(f"jf:alert:{key}", 1, nx=True, ex=ttl)
    except Exception:
        first = True
    if first:
        details = " ".join(f"{k}={v}" for k, v in fields.items())
        alerts.warning("%s %s", code, details)
    return bool(first)
