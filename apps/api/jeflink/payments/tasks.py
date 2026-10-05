"""Tâches Celery des paiements (spec 005). Idempotentes."""

from celery import shared_task

from . import services


@shared_task(acks_late=True)
def watch_settlements() -> int:
    """Alerte l'Ops si des déclarations attendent une décision depuis trop longtemps ; toutes
    les heures."""
    return services.watch_settlements()


@shared_task(acks_late=True)
def purge_payer_last4() -> int:
    """Efface les 4 derniers chiffres du payeur 12 mois après la décision ; tous les jours."""
    return services.purge_payer_last4()
