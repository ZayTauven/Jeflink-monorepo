from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from jeflink.catalog.models import Trade
from jeflink.common.api.reference import LocalizedTextField, LocalizedTextSerializer


class TradeSummarySerializer(serializers.Serializer):
    """Métier dans une liste : de quoi chercher et afficher, hors ligne compris."""

    slug = serializers.CharField()
    name = LocalizedTextField("name")
    short_description = LocalizedTextField("short_description", optional=True)
    icon_key = serializers.SerializerMethodField()
    aliases = serializers.ListField(child=serializers.CharField())

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_icon_key(self, trade: Trade) -> str | None:
        return trade.icon_key or None


class ServiceSerializer(serializers.Serializer):
    slug = serializers.CharField()
    name = LocalizedTextField("name")
    aliases = serializers.ListField(child=serializers.CharField())
    # Prix de départ indicatif : toujours affiché avec « le prix final est dans le devis ».
    price_from_xof = serializers.IntegerField(allow_null=True)
    urgent = serializers.BooleanField()


class TradeDetailSerializer(TradeSummarySerializer):
    seo_title = serializers.SerializerMethodField()
    services = ServiceSerializer(many=True, source="services.all")
    zones = serializers.ListField(child=serializers.CharField(), source="open_zone_slugs")

    @extend_schema_field(LocalizedTextSerializer)
    def get_seo_title(self, trade: Trade) -> dict[str, str | None]:
        return {
            "fr": trade.seo_title_fr or trade.name_fr,
            "wo": trade.seo_title_wo or trade.name_wo or None,
        }
