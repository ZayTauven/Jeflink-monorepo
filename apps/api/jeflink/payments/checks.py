"""Vérification au démarrage : aucun canal de règlement factice hors ``local`` et ``test``."""

from django.conf import settings
from django.core.checks import Error, Tags, register
from django.db import DatabaseError

from .gateways import FAKE_ALLOWED_ENVS


@register(Tags.database)
def fake_channels(app_configs, databases=None, **kwargs) -> list[Error]:
    if settings.DJANGO_ENV in FAKE_ALLOWED_ENVS:
        return []
    if not databases or "default" not in databases:
        return []
    from .models import Gateway, SettlementChannel

    try:
        found = SettlementChannel.objects.filter(gateway=Gateway.FAKE).exists()
    except DatabaseError:
        return []  # base neuve, migrations pas encore appliquées
    if found:
        return [Error("Un canal de règlement factice existe hors local/test.", id="payments.E001")]
    return []
