"""Écritures du catalogue (spec 002) : admin Django et données de départ passent par ici."""

from django.core.exceptions import ValidationError
from django.db import transaction

from jeflink.common.search import clean_aliases

from .models import Service, Trade


def _refuse_slug_change(instance: Trade | Service) -> None:
    if instance.pk is None:
        return
    stored = type(instance).objects.filter(pk=instance.pk).values_list("slug", flat=True).first()
    if stored is not None and stored != instance.slug:
        raise ValidationError({"slug": ValidationError("slug figé", code="slug_frozen")})


@transaction.atomic
def save_trade(*, trade: Trade) -> Trade:
    """Crée ou modifie un métier : slug figé, alias nettoyés, contraintes vérifiées."""
    _refuse_slug_change(trade)
    trade.aliases = clean_aliases(trade.aliases)
    trade.full_clean()
    trade.save()
    return trade


@transaction.atomic
def save_service(*, service: Service) -> Service:
    """Crée ou modifie un service d'un métier ; même règles que ``save_trade``."""
    _refuse_slug_change(service)
    service.aliases = clean_aliases(service.aliases)
    service.full_clean()
    service.save()
    return service


@transaction.atomic
def seed_trades() -> tuple[int, int]:
    """Crée les métiers et services de départ qui manquent (par slug), sans écraser une saisie.

    Renvoie (métiers créés, services créés).
    """
    from .reference_data import TRADES

    trades_created = services_created = 0
    for trade_position, data in enumerate(TRADES, start=1):
        trade = Trade.objects.filter(slug=data["slug"]).first()
        if trade is None:
            fields = {k: v for k, v in data.items() if k != "services"}
            trade = save_trade(trade=Trade(position=trade_position, **fields))
            trades_created += 1
        existing = set(trade.services.values_list("slug", flat=True))
        for service_position, service_data in enumerate(data.get("services", []), start=1):
            if service_data["slug"] in existing:
                continue
            save_service(service=Service(trade=trade, position=service_position, **service_data))
            services_created += 1
    return trades_created, services_created
