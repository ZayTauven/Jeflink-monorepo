"""Écritures des zones (spec 002) : admin Django et données de départ passent par ici."""

from django.contrib.gis.geos import Point
from django.core.exceptions import ValidationError
from django.db import transaction

from jeflink.catalog.models import Trade
from jeflink.common.search import clean_aliases

from .models import City, Zone


def _refuse_slug_change(instance: City | Zone) -> None:
    if instance.pk is None:
        return
    stored = type(instance).objects.filter(pk=instance.pk).values_list("slug", flat=True).first()
    if stored is not None and stored != instance.slug:
        raise ValidationError({"slug": ValidationError("slug figé", code="slug_frozen")})


@transaction.atomic
def save_city(*, city: City) -> City:
    _refuse_slug_change(city)
    city.full_clean()
    city.save()
    return city


@transaction.atomic
def save_zone(*, zone: Zone) -> Zone:
    """Crée ou modifie une zone : slug figé, alias nettoyés, rayon borné."""
    _refuse_slug_change(zone)
    zone.aliases = clean_aliases(zone.aliases)
    zone.full_clean()
    zone.save()
    return zone


@transaction.atomic
def open_trade_in_all_zones(*, trade: Trade) -> int:
    """Ouvre un métier dans toutes les zones actives (« Ouvrir partout »). Renvoie les ajouts."""
    zones = Zone.objects.filter(is_active=True).exclude(trades=trade)
    added = list(zones)
    trade.zones.add(*added)
    return len(added)


@transaction.atomic
def seed_zones(*, open_trades: bool) -> int:
    """Crée la ville et les zones de départ qui manquent (par slug), sans jamais écraser une saisie.

    ``open_trades`` ouvre tous les métiers dans les zones créées ici (en local) ; sinon l'Ops les
    ouvre selon les pros recrutés. Renvoie le nombre de zones créées.
    """
    from .reference_data import CITY, ZONES

    city = City.objects.filter(slug=CITY["slug"]).first() or save_city(city=City(**CITY))
    trades = list(Trade.objects.all()) if open_trades else []
    created = 0
    for data in ZONES:
        if Zone.objects.filter(slug=data["slug"]).exists():
            continue
        fields = {k: v for k, v in data.items() if k not in {"lat", "lon"}}
        zone = save_zone(
            zone=Zone(city=city, center=Point(data["lon"], data["lat"], srid=4326), **fields)
        )
        zone.trades.add(*trades)
        created += 1
    return created
