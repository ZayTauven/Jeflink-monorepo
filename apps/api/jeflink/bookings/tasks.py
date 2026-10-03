"""Tâches Celery des réservations (spec 003). Idempotentes."""

from celery import shared_task

from . import services


@shared_task(acks_late=True)
def cancel_unconfirmed() -> int:
    """Annule les réservations dont le pro n'a pas confirmé à temps ; toutes les 5 minutes."""
    return services.cancel_unconfirmed()
