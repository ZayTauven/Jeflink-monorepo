"""Sérialiseurs de la demande et des devis (spec 003) : client et pro, deux vues distinctes.

Aucune logique métier. La vue du pro n'a **aucun** champ pour le nom, le numéro, le repère ou la
position du client : ils ne peuvent pas fuir par oubli. Le masquage des numéros dans un texte
libre (``mask_numbers``) est de la présentation.
"""

from typing import Any

from django.conf import settings
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from jeflink.bookings.api.serializers import ClientBookingSerializer, ClientProviderSerializer
from jeflink.requests.models import Quote, ServiceRequest
from jeflink.requests.selectors import effective_status

from .refs import (
    QuoteLineSerializer,
    ServiceRefSerializer,
    TradeRefSerializer,
    ZoneRefSerializer,
    masked,
)

# --- Création de la demande --------------------------------------------------------------------


class LocationSerializer(serializers.Serializer):
    """Position du client : envoyée seulement dans le ``POST``, jamais journalisée."""

    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)


class RequestCreateSerializer(serializers.Serializer):
    trade_slug = serializers.CharField(max_length=50)
    service_slug = serializers.CharField(max_length=50, required=False, allow_null=True)
    # Un quartier : par slug (liste), par texte libre, ou déduit de la position.
    zone_slug = serializers.CharField(max_length=50, required=False, allow_null=True)
    zone_text = serializers.CharField(
        max_length=80, required=False, allow_null=True, allow_blank=True
    )
    location = LocationSerializer(required=False, allow_null=True)
    landmark = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    description = serializers.CharField(
        max_length=1000, required=False, allow_blank=True, default=""
    )
    # Absent : celui du service choisi.
    urgent = serializers.BooleanField(required=False, allow_null=True, default=None)
    # Valeurs vérifiées par le service (422 slot_invalid) : asap | date, morning | afternoon |
    # evening | any.
    preferred_when = serializers.CharField(max_length=8, required=False, default="asap")
    preferred_date = serializers.DateField(required=False, allow_null=True, default=None)
    preferred_period = serializers.CharField(max_length=12, required=False, default="any")


class ReasonSerializer(serializers.Serializer):
    """Annulation : un motif de la liste fermée, et une note si le motif est ``other``."""

    reason = serializers.CharField(max_length=24)
    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


# --- Vue du client -----------------------------------------------------------------------------


class ClientQuoteLineSerializer(QuoteLineSerializer):
    """Ligne de devis vue du client : le libellé suit la règle du message (numéros masqués)."""

    label = serializers.SerializerMethodField()

    def get_label(self, line) -> str:
        disclosed = line.quote_id in self.context.get("disclosed_quotes", ())
        return masked(line.label, disclosed=disclosed)


class ClientQuoteSerializer(serializers.ModelSerializer):
    provider = ClientProviderSerializer()
    lines = ClientQuoteLineSerializer(many=True)
    message = serializers.SerializerMethodField()

    class Meta:
        model = Quote
        fields = [
            "public_id",
            "status",
            "kind",
            "total_xof",
            "visit_deductible",
            "message",
            "slot_start",
            "slot_end",
            "valid_until",
            "provider",
            "lines",
        ]
        read_only_fields = fields

    def get_message(self, quote: Quote) -> str:
        """Numéros masqués tant que le pro n'a pas confirmé ce devis."""
        disclosed = quote.pk in self.context.get("disclosed_quotes", ())
        return masked(quote.message, disclosed=disclosed)


class ClientRequestSummarySerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    trade = TradeRefSerializer()
    service = ServiceRefSerializer(allow_null=True)
    zone = ZoneRefSerializer(allow_null=True)

    class Meta:
        model = ServiceRequest
        fields = [
            "public_id",
            "status",
            "trade",
            "service",
            "zone",
            "urgent",
            "created_at",
            "expires_at",
        ]
        read_only_fields = fields

    def get_status(self, request: ServiceRequest) -> str:
        return effective_status(request)


class ClientRequestSerializer(ClientRequestSummarySerializer):
    """Détail : la demande, ses devis (3 au plus) et sa réservation active, en un seul appel."""

    has_location = serializers.SerializerMethodField()
    quotes = serializers.SerializerMethodField()
    booking = serializers.SerializerMethodField()

    class Meta(ClientRequestSummarySerializer.Meta):
        fields = [
            *ClientRequestSummarySerializer.Meta.fields,
            "landmark",
            "has_location",
            "description",
            "preferred_when",
            "preferred_date",
            "preferred_period",
            "channel",
            "first_quoted_at",
            "quotes",
            "booking",
        ]
        read_only_fields = fields

    def get_has_location(self, request: ServiceRequest) -> bool:
        return request.location is not None

    @extend_schema_field(ClientQuoteSerializer(many=True))
    def get_quotes(self, request: ServiceRequest) -> list[dict[str, Any]]:
        return ClientQuoteSerializer(
            self.context.get("quotes", []), many=True, context=self.context
        ).data

    @extend_schema_field(ClientBookingSerializer(allow_null=True))
    def get_booking(self, request: ServiceRequest) -> dict[str, Any] | None:
        booking = self.context.get("booking")
        return ClientBookingSerializer(booking, context=self.context).data if booking else None


# --- Vue du pro, avant la confirmation : jamais le client --------------------------------------


class ProRequestSerializer(serializers.ModelSerializer):
    """Une demande « pour moi » : métier, zone, description (numéros masqués), places restantes.

    Aucun champ du client : ni nom, ni numéro, ni repère, ni position."""

    trade = TradeRefSerializer()
    service = ServiceRefSerializer(allow_null=True)
    zone = ZoneRefSerializer()
    description = serializers.SerializerMethodField()
    places_left = serializers.SerializerMethodField()
    places_total = serializers.SerializerMethodField()

    class Meta:
        model = ServiceRequest
        fields = [
            "public_id",
            "trade",
            "service",
            "zone",
            "description",
            "urgent",
            "preferred_when",
            "preferred_date",
            "preferred_period",
            "expires_at",
            "created_at",
            "places_left",
            "places_total",
        ]
        read_only_fields = fields

    def get_description(self, request: ServiceRequest) -> str:
        return masked(request.description, disclosed=False)

    def get_places_left(self, request: ServiceRequest) -> int:
        return max(0, settings.QUOTE_MAX_ACTIVE - getattr(request, "active_quotes", 0))

    def get_places_total(self, request: ServiceRequest) -> int:
        return settings.QUOTE_MAX_ACTIVE


# --- Devis du pro ------------------------------------------------------------------------------


class QuoteLineInputSerializer(serializers.Serializer):
    # Valeurs vérifiées par le service (422 quote_total_invalid).
    kind = serializers.CharField(max_length=6)
    amount_xof = serializers.IntegerField()
    label = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")


class QuoteCreateSerializer(serializers.Serializer):
    kind = serializers.CharField(max_length=5)
    total_xof = serializers.IntegerField()
    lines = QuoteLineInputSerializer(many=True)
    # Un jour et une plage (heure de Dakar) : le service en tire le créneau en UTC.
    slot_day = serializers.DateField()
    slot_period = serializers.CharField(max_length=12)
    message = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    visit_deductible = serializers.BooleanField(required=False, default=False)


class ProQuoteSerializer(serializers.ModelSerializer):
    request = serializers.SlugRelatedField(slug_field="public_id", read_only=True)
    trade = TradeRefSerializer(source="request.trade")
    zone = ZoneRefSerializer(source="request.zone")
    lines = QuoteLineSerializer(many=True)

    class Meta:
        model = Quote
        fields = [
            "public_id",
            "request",
            "trade",
            "zone",
            "status",
            "kind",
            "total_xof",
            "visit_deductible",
            "message",
            "slot_start",
            "slot_end",
            "valid_until",
            "lines",
            "created_at",
        ]
        read_only_fields = fields
