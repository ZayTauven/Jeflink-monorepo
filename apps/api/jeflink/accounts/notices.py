"""SMS d'information sans code (spec 001, « Tâches Celery » : ``send_notice_sms``).

Ces SMS sont envoyés **au mieux** : ils consomment le budget SMS du numéro (tous motifs, S8),
mais un budget épuisé ne fait jamais échouer l'action qui les déclenche. L'appelant ne sait
pas si le SMS part : il ne peut donc rien apprendre de l'activité d'un numéro (S19).

Ils ont leurs propres sous-budgets (total, préfixe, bloc de 1 000 numéros) et ne partent
jamais quand un plafond partagé est déjà utilisé à moitié : ils ne prennent pas la marge des
connexions (revue sécurité tâche 12, I3).

**SMS de sécurité** (changement de numéro) : seule alerte de la victime, ils ne doivent pas
pouvoir être étouffés en saturant les plafonds du numéro. Ils ne comptent que dans les plafonds
quotidiens globaux, avec repli en base si Redis tombe (revue sécurité tâche 16, I2).
"""

import logging

from django.conf import settings
from django.db import transaction

from jeflink.common.errors import DomainError
from jeflink.common.pii import phone_hmac
from jeflink.common.ratelimit import Limit, RateLimitUnavailable, consume

from .models import NoticeSms
from .otp_limits import (
    _region_cap,
    number_block,
    operator_prefix,
    reserve_sms,
    shared_caps_have_margin,
)
from .phone import phone_region

logger = logging.getLogger(__name__)


def _notice_checks(kind: str, phone: str) -> list[tuple[Limit, str]]:
    """Sous-budgets des SMS d'information, consommés avec les plafonds communs (atomique)."""
    checks = [
        (Limit("notice:daily_total", settings.SMS_NOTICE_DAILY_CAP, 86400), "all"),
        (Limit("notice:prefix_1h", settings.SMS_NOTICE_PREFIX_HOURLY_CAP, 3600),
         operator_prefix(phone)),
        (Limit("notice:block_1h", settings.SMS_NOTICE_BLOCK_HOURLY_CAP, 3600),
         number_block(phone)),
    ]  # fmt: skip
    if kind == NoticeSms.Kind.INVITATION:
        checks.append(
            (
                Limit(
                    "notice:invitation_phone_24h", settings.INVITATION_SMS_PER_PHONE_DAILY, 86400
                ),
                phone,
            )
        )
    return checks


SECURITY_KINDS = frozenset({NoticeSms.Kind.PHONE_CHANGED, NoticeSms.Kind.PHONE_CHANGE_REQUESTED})


def _reserve_security(phone: str, region: str) -> None:
    """Plafonds quotidiens globaux seulement ; sans Redis, comptage en base (jamais ouvert)."""
    from .otp import db_counts

    daily = settings.SMS_DAILY_CAP
    regional = _region_cap(region)
    try:
        outcome = consume(
            [
                (Limit("sms:daily_total", daily, 86400), "all"),
                (Limit("sms:daily_region", regional, 86400), region),
            ]
        )
    except RateLimitUnavailable:
        counts = db_counts(phone, region)
        if counts.total_last_day >= daily or counts.region_last_day >= regional:
            raise DomainError("otp_temporarily_unavailable", status=503) from None
        return
    if not outcome.allowed:
        raise DomainError("otp_temporarily_unavailable", status=503)


def _skip(kind: str, reason: str) -> None:
    logger.info("notice_sms skipped kind=%s reason=%s", kind, reason)


def queue_notice(*, kind: str, phone: str, language: str = "fr") -> NoticeSms | None:
    """Réserve le budget et programme l'envoi après commit. None si le SMS est écarté."""
    region = phone_region(phone)
    try:
        if kind in SECURITY_KINDS:
            _reserve_security(phone, region)
        elif not shared_caps_have_margin(phone, region):
            _skip(kind, "shared_caps_margin")
            return None
        else:
            # Sans Redis, aucun SMS d'information : pas de repli en base (refus → écarté).
            reserve_sms(
                phone=phone,
                region=region,
                new_challenge=False,
                fallback=None,
                extra_checks=_notice_checks(kind, phone),
            )
    except DomainError as exc:
        _skip(kind, exc.code)
        return None
    except RateLimitUnavailable:
        _skip(kind, "ratelimit_unavailable")
        return None
    notice = NoticeSms.objects.create(
        kind=kind,
        phone=phone,
        phone_hmac=phone_hmac(phone),
        region=region,
        language=language if language in {"fr", "wo"} else "fr",
    )
    notice_id = str(notice.public_id)

    def _enqueue() -> None:
        from .tasks import send_notice_sms

        send_notice_sms.delay(notice_id)

    # Broker indisponible : l'action a réussi, le SMS reste « en file » et la purge le ferme
    # (tâche 18). Jamais d'erreur 500 renvoyée au pro pour un SMS au mieux (revue, M4).
    transaction.on_commit(_enqueue, robust=True)
    return notice
