"""Écritures du domaine ``payments`` (spec 005). ``payments`` appelle ``wallet``, jamais
l'inverse (ADR 0012)."""

from django.core.exceptions import ValidationError
from django.db import transaction

from jeflink.trust.services import audit

from .models import SettlementChannel


@transaction.atomic
def save_channel(*, channel: SettlementChannel, operator) -> SettlementChannel:
    """Crée ou modifie un canal de règlement : slug figé, contraintes vérifiées, audité. Un canal
    ne se supprime pas : on le désactive."""
    created = channel.pk is None
    if not created:
        stored = SettlementChannel.objects.filter(pk=channel.pk).values_list("slug", "gateway")
        if (row := stored.first()) is not None and row != (channel.slug, channel.gateway):
            raise ValidationError("Le slug et la passerelle d'un canal sont figés.")
    channel.full_clean()
    channel.save()
    audit(
        action="payments.channel.saved",
        actor=operator,
        target=channel,
        metadata={
            "slug": channel.slug,
            "gateway": channel.gateway,
            "is_active": channel.is_active,
            "created": created,
        },
    )
    return channel
