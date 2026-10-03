"""Tâches Celery de la demande (spec 003). Idempotentes : relançables sans effet double."""

from celery import shared_task

from . import services


@shared_task(acks_late=True)
def expire_due() -> int:
    """Expire les demandes échues (``no_quote`` si aucun devis) ; toutes les 5 minutes."""
    return services.expire_due()


@shared_task(acks_late=True)
def purge_locations() -> int:
    """Vide repère et position des demandes closes sans réservation (30 jours) ; quotidien."""
    return services.purge_locations()
