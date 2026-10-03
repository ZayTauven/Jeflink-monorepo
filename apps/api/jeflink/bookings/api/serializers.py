"""Sérialiseurs des réservations (spec 003) : une vue pour le client, une pour le pro.

Aucune logique métier. Le contact (numéro du pro, nom, numéro, repère et position du client) n'est
renvoyé qu'à partir de ``scheduled`` (``DISCLOSED_STATUSES``), jamais après une annulation.
"""

from typing import Any

from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from jeflink.bookings.machine import DISCLOSED_STATUSES, Actor
from jeflink.bookings.models import Booking, NoShowReport
from jeflink.bookings.services import (
    can_report_no_show,
    contest_deadline,
    no_show_available_at,
)
from jeflink.requests.api.refs import (
    ServiceRefSerializer,
    TradeRefSerializer,
    ZoneRefSerializer,
    masked,
)

# Étapes horodatées (UTC) et fin de la fenêtre de contestation : nulles tant qu'elles n'ont pas eu
# lieu. Mêmes champs pour le client et le pro.
TIMELINE_FIELDS = (
    "en_route_at",
    "on_site_at",
    "started_at",
    "completed_at",
    "closed_at",
    "dispute_deadline",
)


class NoShowStateSerializer(serializers.Serializer):
    """État d'un « le pro n'est pas venu ». Le pro voit en plus l'échéance de contestation."""

    status = serializers.ChoiceField(choices=NoShowReport.Status.choices)
    contest_deadline = serializers.DateTimeField(allow_null=True)
    can_contest = serializers.BooleanField()


def no_show_state(booking: Booking, *, for_pro: bool) -> dict | None:
    report = getattr(booking, "no_show", None)
    if report is None:
        return None
    pending = report.status == NoShowReport.Status.PENDING
    return {
        "status": report.status,
        "contest_deadline": contest_deadline(report) if for_pro and pending else None,
        "can_contest": for_pro and pending and timezone.now() <= contest_deadline(report),
    }


class ClientProviderSerializer(serializers.Serializer):
    """Le pro, tel que le client le voit avant la confirmation : nom commercial et badge."""

    business_name = serializers.CharField()
    verified = serializers.SerializerMethodField()

    def get_verified(self, provider) -> bool:
        return provider.status == "verified"


class ClientContactSerializer(serializers.Serializer):
    """Le pro une fois la réservation planifiée : nom commercial et numéro (E.164)."""

    business_name = serializers.CharField()
    phone = serializers.CharField()


class ClientBookingSerializer(serializers.ModelSerializer):
    request = serializers.SlugRelatedField(slug_field="public_id", read_only=True)
    trade = TradeRefSerializer(source="request.trade")
    zone = ZoneRefSerializer(source="request.zone")
    provider = ClientProviderSerializer()
    quote = serializers.SlugRelatedField(slug_field="public_id", read_only=True)
    contact = serializers.SerializerMethodField()
    payment = serializers.SerializerMethodField()
    cancel_reason = serializers.SerializerMethodField()
    can_report_no_show = serializers.SerializerMethodField()
    no_show_available_at = serializers.SerializerMethodField()
    no_show = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = [
            "public_id",
            "request",
            "status",
            "trade",
            "zone",
            "provider",
            "quote",
            "amount_xof",
            "slot_start",
            "slot_end",
            "confirm_deadline",
            "contact",
            "payment",
            "can_report_no_show",
            "no_show_available_at",
            "no_show",
            *TIMELINE_FIELDS,
            "cancelled_by",
            "cancel_reason",
            "created_at",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.CharField())
    def get_cancel_reason(self, booking: Booking) -> str:
        """Message neutre : si le pro (ou le système) annule, le client ne voit jamais le motif
        (``too_far``, ``job_mismatch``…), seulement ``pro_withdrew``. Ses propres motifs restent."""
        if booking.cancelled_by in {Actor.PRO, Actor.SYSTEM}:
            return "pro_withdrew"
        return booking.cancel_reason

    @extend_schema_field(serializers.BooleanField())
    def get_can_report_no_show(self, booking: Booking) -> bool:
        return can_report_no_show(booking)

    @extend_schema_field(serializers.DateTimeField())
    def get_no_show_available_at(self, booking: Booking) -> Any:
        """Heure (UTC) dès laquelle « Il n'est pas venu » est permis : fin du créneau + marge."""
        return no_show_available_at(booking)

    @extend_schema_field(NoShowStateSerializer(allow_null=True))
    def get_no_show(self, booking: Booking) -> dict | None:
        return no_show_state(booking, for_pro=False)

    @extend_schema_field(ClientContactSerializer(allow_null=True))
    def get_contact(self, booking: Booking) -> dict[str, str] | None:
        """Le numéro du pro n'est partagé qu'à ``scheduled`` (et jamais après une annulation)."""
        if booking.status not in DISCLOSED_STATUSES:
            return None
        return {
            "business_name": booking.provider.business_name,
            "phone": booking.provider.owner.phone or "",
        }

    @extend_schema_field(serializers.CharField())
    def get_payment(self, booking: Booking) -> str:
        """Mention fixe : « À régler au pro, en espèces ou par mobile money. Jeflink ne garde
        aucun argent pour l'instant. » La phrase est une clé i18n côté front."""
        return "direct_to_pro"


class ProClientContactSerializer(serializers.Serializer):
    """Le client, une fois la réservation planifiée : nom et numéro (E.164)."""

    display_name = serializers.CharField()
    phone = serializers.CharField()


class LocationOutSerializer(serializers.Serializer):
    lat = serializers.FloatField()
    lon = serializers.FloatField()


class ProBookingSerializer(serializers.ModelSerializer):
    """La réservation vue du pro. Avant ``scheduled`` : ni nom, ni numéro, ni repère, ni position
    du client, et les numéros de la description sont masqués."""

    request = serializers.SlugRelatedField(slug_field="public_id", read_only=True)
    trade = TradeRefSerializer(source="request.trade")
    service = ServiceRefSerializer(source="request.service", allow_null=True)
    zone = ZoneRefSerializer(source="request.zone")
    urgent = serializers.BooleanField(source="request.urgent")
    description = serializers.SerializerMethodField()
    client = serializers.SerializerMethodField()
    landmark = serializers.SerializerMethodField()
    location = serializers.SerializerMethodField()
    no_show = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = [
            "public_id",
            "request",
            "status",
            "trade",
            "service",
            "zone",
            "urgent",
            "description",
            "amount_xof",
            "slot_start",
            "slot_end",
            "confirm_deadline",
            "client",
            "landmark",
            "location",
            "no_show",
            *TIMELINE_FIELDS,
            "cancelled_by",
            "cancel_reason",
            "created_at",
        ]
        read_only_fields = fields

    @extend_schema_field(NoShowStateSerializer(allow_null=True))
    def get_no_show(self, booking: Booking) -> dict | None:
        return no_show_state(booking, for_pro=True)

    @staticmethod
    def _disclosed(booking: Booking) -> bool:
        return booking.status in DISCLOSED_STATUSES

    def get_description(self, booking: Booking) -> str:
        return masked(booking.request.description, disclosed=self._disclosed(booking))

    @extend_schema_field(ProClientContactSerializer(allow_null=True))
    def get_client(self, booking: Booking) -> dict[str, str] | None:
        if not self._disclosed(booking):
            return None
        return {"display_name": booking.client.display_name, "phone": booking.client.phone or ""}

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_landmark(self, booking: Booking) -> str | None:
        return booking.request.landmark if self._disclosed(booking) else None

    @extend_schema_field(LocationOutSerializer(allow_null=True))
    def get_location(self, booking: Booking) -> dict[str, Any] | None:
        point = booking.request.location
        if not self._disclosed(booking) or point is None:
            return None
        return {"lat": point.y, "lon": point.x}


# --- Entrées du pro ----------------------------------------------------------------------------


class OccurredAtSerializer(serializers.Serializer):
    """Heure de l'appareil (file hors ligne, étape 6) : métadonnée, le serveur fait foi."""

    occurred_at = serializers.DateTimeField(required=False, allow_null=True, default=None)


class StartSerializer(OccurredAtSerializer):
    # La file de l'appareil enverra les photos « avant » plus tard.
    photos_pending = serializers.BooleanField(required=False, default=False)


class ContestNoShowSerializer(serializers.Serializer):
    # Longueur et numéros vérifiés par le service (422 note_invalid).
    note = serializers.CharField(max_length=500, allow_blank=True)
