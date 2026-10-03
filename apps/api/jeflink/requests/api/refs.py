"""Références partagées par les sérialiseurs de la demande, des devis et des réservations."""

from rest_framework import serializers

from jeflink.common.api.reference import LocalizedTextField
from jeflink.common.pii import mask_numbers
from jeflink.requests.models import QuoteLine


def masked(text: str, *, disclosed: bool) -> str:
    """Numéros masqués à l'affichage tant que le pro n'a pas confirmé (texte stocké intact)."""
    return text if disclosed else mask_numbers(text)[0]


class TradeRefSerializer(serializers.Serializer):
    slug = serializers.CharField()
    name = LocalizedTextField("name")


class ServiceRefSerializer(serializers.Serializer):
    slug = serializers.CharField()
    name = LocalizedTextField("name")


class ZoneRefSerializer(serializers.Serializer):
    slug = serializers.CharField()
    name = serializers.CharField()


class QuoteLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuoteLine
        fields = ["kind", "label", "amount_xof"]
        read_only_fields = fields
