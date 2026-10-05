"""Lectures du domaine ``payments`` (spec 005)."""

from django.db.models import QuerySet

from jeflink.common.errors import DomainError

from .models import Gateway, PaymentIntent, SettlementChannel

# Canaux qu'un pro voit et déclare (les espèces se remettent au bureau, saisies par l'Ops).
PRO_VISIBLE_GATEWAYS = (Gateway.MANUAL_MOBILE_MONEY, Gateway.FAKE)


def channels_for_pro() -> QuerySet[SettlementChannel]:
    return SettlementChannel.objects.filter(
        is_active=True, gateway__in=PRO_VISIBLE_GATEWAYS
    ).order_by("position", "slug")


def channel_by_slug(slug: str) -> SettlementChannel:
    channel = SettlementChannel.objects.filter(slug=slug).first()
    if channel is None:
        raise DomainError("channel_inactive", status=422)
    return channel


def intents_for_provider(provider) -> QuerySet[PaymentIntent]:
    return (
        PaymentIntent.objects.filter(provider=provider)
        .select_related("channel")
        .order_by("-created_at")
    )


def intent_for_provider(*, provider, public_id) -> PaymentIntent:
    """Règlement du pro ; celui d'un autre répond ``not_found``."""
    intent = intents_for_provider(provider).filter(public_id=public_id).first()
    if intent is None:
        raise DomainError("not_found", status=404)
    return intent
