"""Lectures des zones (spec 002) : le contrat sur lequel s'appuient la demande, l'IA1 et le SEO.

Aucune coordonnée d'utilisateur n'est journalisée ni renvoyée : seulement des zones.
"""

import re
from dataclasses import dataclass, field

from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from django.db.models import F, Q, QuerySet

from jeflink.catalog.models import Trade
from jeflink.catalog.selectors import active_trades
from jeflink.common.errors import DomainError
from jeflink.common.search import match, normalize

from .models import Zone

ZONE_TEXT_MAX_LENGTH = 40
_DIGITS = re.compile(r"\d+")


def active_zones(*, city_slug: str | None = None) -> QuerySet[Zone]:
    """Zones actives de villes actives, par popularité puis nom."""
    zones = Zone.objects.filter(is_active=True, city__is_active=True).select_related("city")
    if city_slug is not None:
        zones = zones.filter(city__slug=city_slug)
    return zones


def active_zone(slug: str) -> Zone:
    zone = active_zones().filter(slug=slug).first()
    if zone is None:
        raise DomainError("zone_not_found", status=404)
    return zone


def trades_in_zone(zone: Zone) -> QuerySet[Trade]:
    """Métiers actifs ouverts dans la zone, avec leurs services actifs."""
    return active_trades().filter(zones=zone)


def open_zone_slugs(trade: Trade) -> list[str]:
    """Slugs des zones actives où le métier est ouvert (pages SEO métier par quartier)."""
    return list(active_zones().filter(trades=trade).values_list("slug", flat=True))


def zones_for_point(point: Point) -> list[Zone]:
    """Zones qui contiennent le point, triées par distance au centre.

    Un ``boundary`` saisi prime sur le cercle. Plusieurs zones : le client choisit, jamais de
    choix automatique silencieux. Liste vide : hors zone.
    """
    if point.srid is None:
        point.srid = 4326
    return list(
        active_zones()
        .annotate(distance_m=Distance("center", point))
        .filter(
            Q(boundary__isnull=False, boundary__contains=point)
            | Q(boundary__isnull=True, distance_m__lte=F("radius_m"))
        )
        .order_by("distance_m", "position", "name")
    )


def nearest_zone(point: Point) -> tuple[Zone, int] | None:
    """Zone active la plus proche et sa distance arrondie au km (signal « hors zone »)."""
    if point.srid is None:
        point.srid = 4326
    zone = (
        active_zones().annotate(distance_m=Distance("center", point)).order_by("distance_m").first()
    )
    if zone is None:
        return None
    return zone, round(zone.distance_m.m / 1000)


def zone_terms(zone: Zone) -> list[str]:
    return [zone.name, zone.slug, *zone.aliases]


def resolve_zone_text(text: str) -> list[Zone]:
    """Zones actives qui répondent au texte du client (« PA », « Sicap »), meilleure d'abord."""
    ranked = [
        (rank, zone.position, zone.name, zone)
        for zone in active_zones()
        if (rank := match(text, zone_terms(zone))) is not None
    ]
    if any(item[0] == 0 for item in ranked):
        # Une égalité (« PA ») l'emporte : les préfixes ne sont que des suggestions.
        ranked = [item for item in ranked if item[0] == 0]
    return [item[-1] for item in sorted(ranked, key=lambda item: item[:3])]


def unknown_zone_text(text: str) -> str:
    """Texte libre gardé pour le signal « demande non servie » : normalisé, sans chiffres."""
    return " ".join(_DIGITS.sub(" ", normalize(text)).split())[:ZONE_TEXT_MAX_LENGTH].strip()


@dataclass(frozen=True)
class Availability:
    """``available`` ou un motif stable, réutilisé par l'événement ``demand.unserved``."""

    status: str
    zone: Zone | None = None
    candidates: list[Zone] = field(default_factory=list)
    zone_text: str | None = None
    nearest_zone_slug: str | None = None
    distance_km: int | None = None

    @property
    def available(self) -> bool:
        return self.status == "available"


def availability(
    *,
    trade_slug: str,
    zone_slug: str | None = None,
    zone_text: str | None = None,
    point: Point | None = None,
) -> Availability:
    """Le métier est-il servi à cet endroit (slug, texte libre ou point) ?

    Motifs : ``trade_not_found``, ``trade_inactive``, ``zone_not_found``, ``zone_inactive``,
    ``zone_unknown`` (texte sans zone), ``out_of_area`` (point hors zone), ``zone_ambiguous``
    (plusieurs zones possibles : le client choisit parmi ``candidates``), ``trade_not_in_zone``.
    """
    if sum(value is not None for value in (zone_slug, zone_text, point)) != 1:
        raise ValueError("un seul parmi zone_slug, zone_text et point")

    trade = Trade.objects.filter(slug=trade_slug).first()
    if trade is None:
        return Availability("trade_not_found")
    if not trade.is_active:
        return Availability("trade_inactive")

    if zone_slug is not None:
        zone = Zone.objects.select_related("city").filter(slug=zone_slug).first()
        if zone is None:
            return Availability("zone_not_found")
        if not (zone.is_active and zone.city.is_active):
            return Availability("zone_inactive")
    else:
        if zone_text is not None:
            candidates = resolve_zone_text(zone_text)
            if not candidates:
                return Availability("zone_unknown", zone_text=unknown_zone_text(zone_text))
        elif point is not None:
            candidates = zones_for_point(point)
            if not candidates:
                nearest = nearest_zone(point)
                if nearest is None:
                    return Availability("out_of_area")
                return Availability(
                    "out_of_area", nearest_zone_slug=nearest[0].slug, distance_km=nearest[1]
                )
        if len(candidates) > 1:
            return Availability("zone_ambiguous", candidates=candidates)
        zone = candidates[0]

    if not zone.trades.filter(pk=trade.pk).exists():
        return Availability("trade_not_in_zone", zone=zone)
    return Availability("available", zone=zone)
