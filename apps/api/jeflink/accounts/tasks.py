"""Tâches Celery du domaine accounts (spec 001, « Tâches Celery » ; ADR 0008).

``send_otp`` ne reçoit qu'un identifiant d'envoi : le code est généré ici, dans le worker,
et ne transite jamais par le broker (S28). Son HMAC est enregistré **avant** l'envoi, pour
qu'un SMS arrivé vite soit vérifiable.
"""

import logging

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from jeflink.notifications.sms import (
    SmsAmbiguousError,
    SmsPermanentError,
    SmsTransientError,
    get_sms_gateway,
)

from .models import OtpChallenge, OtpDelivery
from .otp import CODE_TTL, hash_code, new_code
from .otp_limits import record_sms_sent
from .sms_templates import otp_sms_body

logger = logging.getLogger(__name__)
MAX_TRANSIENT_RETRIES = 3


@shared_task(bind=True, max_retries=MAX_TRANSIENT_RETRIES, acks_late=True)
def send_otp(self, delivery_public_id: str) -> None:
    with transaction.atomic():
        delivery = (
            OtpDelivery.objects.select_for_update()
            .select_related("challenge")
            .filter(public_id=delivery_public_id)
            .first()
        )
        if delivery is None or delivery.status != OtpDelivery.Status.QUEUED:
            return  # idempotent : déjà envoyé, échoué ou d'issue inconnue
        challenge = delivery.challenge
        now = timezone.now()
        if challenge.status != OtpChallenge.Status.PENDING or now >= challenge.expires_at:
            delivery.status = OtpDelivery.Status.FAILED
            delivery.error_code = "challenge_closed"
            delivery.save(update_fields=["status", "error_code", "updated_at"])
            return
        # Nouveau code à chaque tentative (y compris après une erreur transitoire).
        code = new_code()
        delivery.code_hash = hash_code(delivery.public_id, code)
        delivery.expires_at = now + CODE_TTL
        delivery.save(update_fields=["code_hash", "expires_at", "updated_at"])

    body = otp_sms_body(
        app=challenge.app, purpose=challenge.purpose, code=code, language=challenge.language
    )
    gateway = get_sms_gateway()
    try:
        result = gateway.send(
            to=challenge.phone,
            body=body,
            idempotency_key=f"otp:{delivery.public_id}:{self.request.retries}",
            sender_id=settings.SMS_SENDER_ID,
        )
    except SmsTransientError as exc:
        # Le code envoyé n'est jamais parti : on l'invalide avant le nouvel essai.
        OtpDelivery.objects.filter(pk=delivery.pk).update(code_hash="", expires_at=None)
        if self.request.retries >= MAX_TRANSIENT_RETRIES:
            _close(delivery, OtpDelivery.Status.FAILED, gateway.name, exc.code or "transient")
            return
        raise self.retry(exc=exc, countdown=2 ** (self.request.retries + 1)) from exc
    except SmsAmbiguousError as exc:
        # Peut-être parti : le code reste valable, aucun nouvel essai (pas de double SMS).
        _close(delivery, OtpDelivery.Status.UNKNOWN, gateway.name, exc.code or "ambiguous")
        return
    except SmsPermanentError as exc:
        OtpDelivery.objects.filter(pk=delivery.pk).update(code_hash="", expires_at=None)
        _close(delivery, OtpDelivery.Status.FAILED, gateway.name, exc.code or "permanent")
        return

    OtpDelivery.objects.filter(pk=delivery.pk).update(
        status=OtpDelivery.Status.SENT,
        gateway=result.gateway,
        provider_message_id=result.provider_message_id[:128],
        segments=result.segments,
        sent_at=timezone.now(),
        updated_at=timezone.now(),
    )
    record_sms_sent(challenge.phone)


def _close(delivery: OtpDelivery, status: str, gateway: str, error_code: str) -> None:
    OtpDelivery.objects.filter(pk=delivery.pk).update(
        status=status, gateway=gateway, error_code=error_code[:64], updated_at=timezone.now()
    )
    logger.warning("send_otp %s delivery=%s error=%s", status, delivery.public_id, error_code[:64])
