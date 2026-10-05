"""Tâches Celery des paiements (spec 005). Idempotentes."""

from celery import shared_task

from . import services


@shared_task(acks_late=True)
def watch_settlements() -> int:
    """Alerte l'Ops si des déclarations attendent une décision depuis trop longtemps ; toutes
    les heures."""
    return services.watch_settlements()
