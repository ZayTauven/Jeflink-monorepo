"""Vérification au démarrage : aucun pro de démo hors ``local`` et ``test`` (spec 003)."""

from django.conf import settings
from django.core.checks import Error, Tags, register
from django.db import DatabaseError


@register(Tags.database)
def demo_providers(app_configs, databases=None, **kwargs) -> list[Error]:
    if settings.DJANGO_ENV in {"local", "test"}:
        return []
    if not databases or "default" not in databases:
        return []
    from .models import Provider

    try:
        found = Provider.objects.filter(is_demo=True).exists()
    except DatabaseError:
        return []  # base neuve, migrations pas encore appliquées
    if found:
        return [Error("Des pros de démo existent hors local/test.", id="providers.E001")]
    return []
