"""Agrégats publics du site (spec 006) : des chiffres à seuils, jamais une personne.

Lecture seule. Les données viennent des sélecteurs de ``bookings``, ``reviews`` et ``providers``
(pros de démo et comptes de revue déjà exclus). Chaque chiffre n'existe qu'au-dessus de son seuil
(``PUBLIC_STATS_*``) et est arrondi : on ne peut jamais en tirer la note ou l'activité d'un seul
artisan. La réponse ne contient ni nom, ni identifiant.
"""

from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db.models import Avg, Count

from jeflink.bookings.selectors import public_closed_bookings
from jeflink.catalog.models import Trade
from jeflink.common.errors import DomainError
from jeflink.providers.selectors import public_verified_providers
from jeflink.reviews.selectors import public_counted_reviews
from jeflink.zones.models import Zone

ROUND_TO = 10


def _round_down(value: int, step: int | None = None) -> int:
    step = step or ROUND_TO
    return value - value % step


def _hours(delta: timedelta) -> int | float:
    hours = delta.total_seconds() / 3600
    return int(hours) if hours == int(hours) else round(hours, 1)


def public_rules() -> dict[str, Any]:
    """Règles réelles des specs 003 et 004, lues dans les réglages : le site ne les recopie pas."""
    start, end = settings.BOOKING_CONFIRM_QUIET_HOURS
    return {
        "max_quotes_per_request": settings.QUOTE_MAX_ACTIVE,
        "dispute_window_hours": _hours(settings.BOOKING_DISPUTE_WINDOW),
        "pro_confirm_hours": _hours(settings.BOOKING_CONFIRM_TTL),
        "pro_confirm_hours_urgent": _hours(settings.BOOKING_CONFIRM_TTL_URGENT),
        "quiet_hours": {"start": start, "end": end},  # heure de Dakar
    }


def _missions(trade: Trade | None, zone: Zone | None) -> int | None:
    bookings = public_closed_bookings(trade=trade, zone=zone)
    count = bookings.count()
    if count < settings.PUBLIC_STATS_MIN_MISSIONS:
        return None
    # Moins de 3 pros : le volume serait celui d'un artisan que l'on peut identifier.
    pros = bookings.order_by().values("provider_id").distinct().count()
    if pros < settings.PUBLIC_STATS_MIN_MISSION_PROS:
        return None
    return _round_down(count)


def _rating(trade: Trade | None, zone: Zone | None) -> dict[str, Any] | None:
    # Jamais avec un quartier : la différence entre deux filtres isolerait un pro.
    if zone is not None:
        return None
    reviews = public_counted_reviews(trade=trade)
    count = reviews.count()
    if count < settings.PUBLIC_STATS_MIN_REVIEWS:
        return None
    # Moins de 3 pros notés : la moyenne serait celle d'un artisan que l'on peut identifier.
    rated_pros = reviews.order_by().values("provider_id").distinct().count()
    if rated_pros < settings.PUBLIC_STATS_MIN_RATED_PROS:
        return None
    # Dominance : un pro qui pèse plus de la moitié des avis fait la note à lui seul.
    top = reviews.order_by().values("provider_id").annotate(n=Count("pk")).order_by("-n")[0]["n"]
    if top > count * settings.PUBLIC_STATS_MAX_PRO_SHARE:
        return None
    average = reviews.order_by().aggregate(average=Avg("rating"))["average"]
    return {"average": round(float(average), 1), "count": _round_down(count)}


def _verified_pros(trade: Trade | None, zone: Zone | None) -> int | None:
    count = public_verified_providers(trade=trade, zone=zone).count()
    filtered = trade is not None or zone is not None
    minimum = (
        settings.PUBLIC_STATS_MIN_PROS_FILTERED if filtered else settings.PUBLIC_STATS_MIN_PROS
    )
    if count < minimum:
        return None
    # Valeur exacte jusqu'à 9, puis à la dizaine inférieure (le site écrit « plus de 20 »).
    return count if count < ROUND_TO else _round_down(count)


def public_stats(trade: Trade | None = None, zone: Zone | None = None) -> dict[str, Any]:
    """Missions, note et pros vérifiés (``None`` sous leur seuil), plus les règles.

    Un quartier seul est refusé (``zone_requires_trade``) : sans le métier, la différence entre
    deux requêtes isolerait un pro. La note n'existe pas avec un quartier.
    """
    if zone is not None and trade is None:
        raise DomainError("zone_requires_trade", status=400)
    return {
        "missions_completed": _missions(trade, zone),
        "rating": _rating(trade, zone),
        "verified_pros": _verified_pros(trade, zone),
        "rules": public_rules(),
    }
