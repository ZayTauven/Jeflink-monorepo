"""Événements de notification (spec 003) : le point d'extension des push et des SMS (étape 6).

``notify(kind, recipients, ref)`` est appelé par les services, **après le commit** de la
transaction en cours. Il ne transporte que le type de l'événement, des ``public_id`` et une
référence (``public_id`` de la demande ou de la réservation) : jamais un nom, un numéro, un
repère, une position ni un texte libre. L'adaptateur décide du canal (rien, journal, push, SMS).

Un échec d'adaptateur n'annule jamais l'action métier qui l'a déclenché.
"""

import logging
import uuid
from collections.abc import Iterable
from typing import Any, Protocol

from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)

# Les cinq types de la spec 003, puis ceux de la spec 004.
REQUEST_NEW = "request.new"
QUOTE_RECEIVED = "quote.received"
BOOKING_TO_CONFIRM = "booking.to_confirm"
BOOKING_SCHEDULED = "booking.scheduled"
BOOKING_CANCELLED = "booking.cancelled"
# Spec 004 : déroulé, code de fin, avenant, no-show, litige, clôture. Les trois premiers partent
# aussi par SMS (le gabarit est rendu côté serveur par l'adaptateur, jamais transporté ici).
COMPLETION_CODE_SMS = "completion_code.sms"
AMENDMENT_PROPOSED = "amendment.proposed"
DISPUTE_REMINDER = "booking.dispute_reminder"
BOOKING_PROGRESS = "booking.progress"
AMENDMENT_DECIDED = "amendment.decided"
BOOKING_COMPLETED = "booking.completed"
BOOKING_COMPLETED_NO_CODE = "booking.completed_no_code"
NO_SHOW_CHECK = "booking.no_show_check"
NO_SHOW_CONTESTED = "no_show.contested"
BOOKING_DISPUTED = "booking.disputed"
DISPUTE_DECIDED = "dispute.decided"
BOOKING_CLOSED = "booking.closed"
# Spec 005 : seuils de la dette de commission du pro (référence : ``public_id`` de la fiche pro).
WALLET_DEBT_ALERT = "wallet.debt_alert"
WALLET_QUOTES_BLOCKED = "wallet.quotes_blocked"
WALLET_QUOTES_UNBLOCKED = "wallet.quotes_unblocked"
SMS_KINDS = frozenset(
    {
        COMPLETION_CODE_SMS,
        AMENDMENT_PROPOSED,
        DISPUTE_REMINDER,
        BOOKING_COMPLETED_NO_CODE,
        WALLET_QUOTES_BLOCKED,
    }
)
KINDS = frozenset(
    {
        REQUEST_NEW, QUOTE_RECEIVED, BOOKING_TO_CONFIRM, BOOKING_SCHEDULED, BOOKING_CANCELLED,
        COMPLETION_CODE_SMS, AMENDMENT_PROPOSED, DISPUTE_REMINDER, BOOKING_PROGRESS,
        AMENDMENT_DECIDED, BOOKING_COMPLETED, BOOKING_COMPLETED_NO_CODE, NO_SHOW_CHECK,
        NO_SHOW_CONTESTED, BOOKING_DISPUTED,
        DISPUTE_DECIDED, BOOKING_CLOSED, WALLET_DEBT_ALERT, WALLET_QUOTES_BLOCKED,
        WALLET_QUOTES_UNBLOCKED,
    }
)  # fmt: skip


class NotificationAdapter(Protocol):
    name: str

    def deliver(self, *, kind: str, recipients: tuple[str, ...], ref: str) -> None: ...


class LogAdapter:
    """Local et test : une ligne par événement, type et ``public_id`` seulement."""

    name = "log"

    def deliver(self, *, kind: str, recipients: tuple[str, ...], ref: str) -> None:
        logger.info("notify kind=%s recipients=%s ref=%s", kind, ",".join(recipients), ref)


class NullAdapter:
    """Aucun envoi : ce que fait un environnement sans canal branché."""

    name = "none"

    def deliver(self, *, kind: str, recipients: tuple[str, ...], ref: str) -> None:
        return None


_ADAPTERS: dict[str, type[NotificationAdapter]] = {"log": LogAdapter, "none": NullAdapter}


def get_adapter() -> NotificationAdapter:
    """Adaptateur choisi par ``NOTIFICATIONS_ADAPTER`` (``log`` par défaut en local et en test,
    ``none`` ailleurs tant que les push et les SMS ne sont pas branchés)."""
    name = getattr(settings, "NOTIFICATIONS_ADAPTER", "") or (
        "log" if settings.DJANGO_ENV in {"local", "test"} else "none"
    )
    try:
        return _ADAPTERS[name]()
    except KeyError:
        raise ValueError(f"adaptateur de notification inconnu : {name}") from None


def _public_id(recipient: Any) -> str:
    public_id = getattr(recipient, "public_id", recipient)
    return str(public_id if isinstance(public_id, uuid.UUID) else uuid.UUID(str(public_id)))


def notify(kind: str, recipients: Iterable[Any], ref: Any) -> None:
    """Planifie l'envoi après le commit. ``recipients`` : des comptes (``User``) ou leurs
    ``public_id`` ; ``ref`` : le ``public_id`` de la demande ou de la réservation."""
    if kind not in KINDS:
        raise ValueError(f"type de notification inconnu : {kind}")
    ids = tuple(dict.fromkeys(_public_id(recipient) for recipient in recipients))
    if not ids:
        return
    reference = _public_id(ref)

    def deliver() -> None:
        try:
            get_adapter().deliver(kind=kind, recipients=ids, ref=reference)
        except Exception:
            # Jamais d'exception dans un callback de commit ; ni message ni contexte (donnée perso).
            logger.error("notify_failed kind=%s ref=%s", kind, reference)

    transaction.on_commit(deliver)
