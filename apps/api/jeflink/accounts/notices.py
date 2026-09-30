"""SMS d'information sans code (spec 001, « Tâches Celery » : ``send_notice_sms``).

Ces SMS sont envoyés **au mieux** : ils consomment le budget SMS du numéro (tous motifs, S8)
et les plafonds globaux, mais un budget épuisé ne fait jamais échouer l'action qui les
déclenche. L'appelant ne sait pas si le SMS part : il ne peut donc rien apprendre de
l'activité d'un numéro (S19).
"""

import logging

from django.conf import settings
from django.db import transaction

from jeflink.common.errors import DomainError
from jeflink.common.pii import phone_hmac
from jeflink.common.ratelimit import Limit, RateLimitUnavailable, consume

from .models import NoticeSms
from .otp_limits import reserve_sms
from .phone import phone_region

logger = logging.getLogger(__name__)


def _kind_limit(kind: str) -> Limit | None:
    if kind == NoticeSms.Kind.INVITATION:
        return Limit("notice:invitation_phone_24h", settings.INVITATION_SMS_PER_PHONE_DAILY, 86400)
    return None


def queue_notice(*, kind: str, phone: str, language: str = "fr") -> NoticeSms | None:
    """Réserve le budget et programme l'envoi après commit. None si le SMS est écarté."""
    region = phone_region(phone)
    limit = _kind_limit(kind)
    try:
        if limit is not None and not consume([(limit, phone)]).allowed:
            logger.info("notice_sms skipped kind=%s reason=kind_limit", kind)
            return None
        # Sans Redis, aucun SMS d'information : pas de repli en base (refus → écarté).
        reserve_sms(phone=phone, region=region, new_challenge=False, fallback=None)
    except (DomainError, RateLimitUnavailable) as exc:
        reason = exc.code if isinstance(exc, DomainError) else "ratelimit_unavailable"
        logger.info("notice_sms skipped kind=%s reason=%s", kind, reason)
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

    transaction.on_commit(_enqueue)
    return notice
