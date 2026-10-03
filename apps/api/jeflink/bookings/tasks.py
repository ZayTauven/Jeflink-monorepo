"""Tâches Celery des réservations (spec 003). Idempotentes."""

from celery import shared_task

from . import services


@shared_task(acks_late=True)
def cancel_unconfirmed() -> int:
    """Annule les réservations dont le pro n'a pas confirmé à temps ; toutes les 5 minutes."""
    return services.cancel_unconfirmed()


@shared_task(acks_late=True)
def close_due() -> int:
    """Clôt les réservations ``completed`` dont la fenêtre de contestation est échue ;
    toutes les 5 minutes."""
    return services.close_due()


@shared_task(acks_late=True)
def remind_disputes() -> int:
    """Prévient le client avant la fin de la fenêtre de contestation ; toutes les 5 minutes."""
    return services.remind_disputes()
