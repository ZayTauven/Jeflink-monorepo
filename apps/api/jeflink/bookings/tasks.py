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


@shared_task(
    acks_late=True, autoretry_for=(Exception,), retry_backoff=True, retry_jitter=True, max_retries=5
)
def make_thumbnail(photo_public_id: str) -> bool:
    """Miniature d'une photo (400 px, WebP). Idempotente ; réessayée si le stockage est en panne."""
    return services.make_thumbnail(photo_public_id=photo_public_id)


@shared_task(acks_late=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def delete_objects(keys: list[str]) -> int:
    """Supprime des objets du stockage (clés faites de ``public_id`` seulement). Idempotente."""
    from jeflink.common import storage

    for key in keys:
        storage.delete(key)
    return len(keys)


@shared_task(acks_late=True)
def purge_photos() -> int:
    """Supprime les photos gardées depuis plus de 12 mois après la clôture ; chaque jour."""
    return services.purge_photos()


@shared_task(acks_late=True)
def purge_contact() -> int:
    """Vide le repère et la position des demandes 90 jours après la clôture ; chaque jour."""
    return services.purge_contact()


@shared_task(acks_late=True)
def flag_stuck() -> int:
    """Signale à l'Ops les réservations restées sur place ou en cours après la fin du créneau."""
    return services.flag_stuck()
