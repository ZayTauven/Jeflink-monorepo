"""Vérification au démarrage : aucune zone ne porte un slug réservé (spec 006, ADR 0013)."""

from django.core.checks import Error, Tags, register
from django.db import DatabaseError

from jeflink.catalog.models import RESERVED_ZONE_SLUGS


@register(Tags.database)
def reserved_zone_slugs(app_configs, databases=None, **kwargs) -> list[Error]:
    if not databases or "default" not in databases:
        return []
    from .models import Zone

    try:
        found = sorted(
            Zone.objects.filter(slug__in=RESERVED_ZONE_SLUGS).values_list("slug", flat=True)
        )
    except DatabaseError:
        return []
    return [
        Error(
            f"La zone « {slug} » porte un slug réservé (catalog/reserved_slugs.json).",
            id="zones.E001",
        )
        for slug in found
    ]
