"""Tâches Celery du portefeuille (spec 005). Idempotentes."""

from celery import shared_task

from . import services


@shared_task(acks_late=True)
def remind_debts() -> int:
    """Relance les pros dont la dette effective dépasse le seuil d'alerte, au plus une fois par
    ``WALLET_REMINDER_EVERY`` ; tous les jours."""
    return services.remind_debts()
