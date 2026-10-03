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


@shared_task(acks_late=True)
def confirm_no_shows() -> int:
    """Confirme les no-shows non contestés dans les 24 h (le poids de fiabilité s'applique alors) ;
    toutes les 5 minutes."""
    return services.confirm_no_shows()


@shared_task(acks_late=True)
def no_show_check() -> int:
    """Demande au client si le pro est venu, une fois le créneau et la marge passés ; toutes les
    5 minutes. La réservation n'est jamais annulée seule : le pro est peut-être venu."""
    return services.no_show_check()
