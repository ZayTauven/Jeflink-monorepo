"""Vérification au démarrage : aucun métier ne porte un slug réservé (spec 006, ADR 0013)."""

from django.core.checks import Error, Tags, register
from django.db import DatabaseError

from .models import RESERVED_TRADE_SLUGS


@register(Tags.database)
def reserved_trade_slugs(app_configs, databases=None, **kwargs) -> list[Error]:
    if not databases or "default" not in databases:
        return []
    from .models import Trade

    try:
        found = sorted(
            Trade.objects.filter(slug__in=RESERVED_TRADE_SLUGS).values_list("slug", flat=True)
        )
    except DatabaseError:
        return []  # base neuve, migrations pas encore appliquées
    return [
        Error(
            f"Le métier « {slug} » porte un slug réservé (catalog/reserved_slugs.json).",
            id="catalog.E001",
        )
        for slug in found
    ]
