"""Vues de la demande et des devis (spec 003) : permissions, désérialisation, service,
sérialisation. Rien d'autre. Un objet d'un autre utilisateur répond 404."""

from typing import Any

from django.contrib.gis.geos import Point
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from jeflink.accounts.permissions import (
    IsClient,
    IsProOwner,
    IsVerifiedPro,
    RequiresCompleteProfile,
)
from jeflink.bookings.machine import DISCLOSED_STATUSES
from jeflink.bookings.selectors import active_booking_for_request, withdrawn_by_provider
from jeflink.common.api.idempotency import IDEMPOTENCY_PARAMETER, idempotency_key
from jeflink.common.client_ip import is_trusted_bff_request
from jeflink.requests.drafts import RequestDraft
from jeflink.requests.models import Quote, ServiceRequest
from jeflink.requests.quotes import QuoteInput, QuoteLineInput, submit_quote, withdraw_quote
from jeflink.requests.selectors import (
    quote_for_provider,
    quotes_for_client_request,
    quotes_for_provider,
    request_for_client,
    request_for_provider,
    requests_for_client,
    requests_for_provider,
)
from jeflink.requests.services import cancel_request, create_request
from jeflink.reviews.selectors import rating_for_providers

from .serializers import (
    ApiErrorSerializer,
    ClientRequestSerializer,
    ClientRequestSummarySerializer,
    ProQuoteSerializer,
    ProRequestSerializer,
    QuoteCreateSerializer,
    ReasonSerializer,
    RequestCreateSerializer,
)

ERRORS = {
    401: OpenApiResponse(description="not_authenticated"),
    403: OpenApiResponse(description="profile_incomplete, role_required, provider_not_verified"),
    404: OpenApiResponse(description="not_found"),
}


def request_detail_data(request_obj: ServiceRequest) -> dict[str, Any]:
    """Le détail embarque ses devis et sa réservation active : un seul appel sur réseau faible."""
    booking = active_booking_for_request(request_obj)
    disclosed = booking is not None and booking.status in DISCLOSED_STATUSES
    quotes = list(quotes_for_client_request(request_obj))
    provider_ids = {quote.provider_id for quote in quotes}
    if booking is not None:
        provider_ids.add(booking.provider_id)
    context = {
        "quotes": quotes,
        "booking": booking,
        # La note de chaque pro (avis publiés), en une requête : « Nouveau sur Jeflink » sous 3.
        "ratings": rating_for_providers(provider_ids),
        "withdrawn_by_provider": withdrawn_by_provider(request_obj, active=booking),
        # Les numéros d'un message de devis ne sont rendus qu'une fois ce pro confirmé.
        "disclosed_quotes": {booking.quote_id} if disclosed else set(),
    }
    return ClientRequestSerializer(request_obj, context=context).data


def _draft(data: dict[str, Any]) -> RequestDraft:
    location = data.get("location")
    return RequestDraft(
        trade_slug=data["trade_slug"],
        service_slug=data.get("service_slug") or None,
        zone_slug=data.get("zone_slug") or None,
        zone_text=data.get("zone_text") or None,
        location=Point(location["lon"], location["lat"], srid=4326) if location else None,
        landmark=data["landmark"],
        description=data["description"],
        urgent=data["urgent"],
        preferred_when=data["preferred_when"],
        preferred_date=data["preferred_date"],
        preferred_period=data["preferred_period"],
    )


def _channel(request: Request) -> str:
    """Le BFF de confiance porte le web ; sinon c'est une app mobile."""
    return "web" if is_trusted_bff_request(request._request) else "app"


class RequestListCreateView(generics.ListCreateAPIView):
    """Mes demandes (liste) et création d'une demande."""

    def get_permissions(self) -> list[BasePermission]:
        if self.request.method == "POST":
            return [RequiresCompleteProfile()]
        return [IsClient()]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return RequestCreateSerializer
        return ClientRequestSummarySerializer

    def get_queryset(self):
        return requests_for_client(user=self.request.user)

    @extend_schema(
        tags=["requests"],
        operation_id="requests_list",
        responses={200: ClientRequestSummarySerializer(many=True), **ERRORS},
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)

    @extend_schema(
        tags=["requests"],
        operation_id="requests_create",
        parameters=[IDEMPOTENCY_PARAMETER],
        request=RequestCreateSerializer,
        responses={
            201: ClientRequestSerializer,
            200: OpenApiResponse(ClientRequestSerializer, description="Rejeu : même demande"),
            400: OpenApiResponse(description="invalid, idempotency_key_required"),
            409: OpenApiResponse(description="request_limit_reached, idempotency_key_reused"),
            422: OpenApiResponse(
                ApiErrorSerializer,
                description=(
                    "zone_ambiguous (+ candidates), trade_not_in_zone, out_of_area, "
                    "trade_not_found, trade_inactive, zone_not_found, zone_inactive, "
                    "zone_required, service_not_in_trade, landmark_or_location_required, "
                    "description_required, slot_invalid"
                ),
            ),
            429: OpenApiResponse(description="request_rate_limited (+ retry_after)"),
            **ERRORS,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = RequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = create_request(
            client=request.user,
            draft=_draft(serializer.validated_data),
            channel=_channel(request),
            idempotency_key=idempotency_key(request),
        )
        code = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
        return Response(request_detail_data(result.request), status=code)


class RequestDetailView(APIView):
    permission_classes = [IsClient]

    @extend_schema(
        tags=["requests"],
        operation_id="requests_retrieve",
        responses={200: ClientRequestSerializer, **ERRORS},
    )
    def get(self, request: Request, public_id) -> Response:
        request_obj = request_for_client(user=request.user, public_id=public_id)
        return Response(request_detail_data(request_obj))


class RequestCancelView(APIView):
    permission_classes = [IsClient]

    @extend_schema(
        tags=["requests"],
        operation_id="requests_cancel",
        request=ReasonSerializer,
        responses={
            200: ClientRequestSerializer,
            409: OpenApiResponse(description="request_closed (réservée : annuler la réservation)"),
            422: OpenApiResponse(description="reason_invalid, note_invalid"),
            **ERRORS,
        },
    )
    def post(self, request: Request, public_id) -> Response:
        request_obj = request_for_client(user=request.user, public_id=public_id)
        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cancel_request(request=request_obj, actor=request.user, **serializer.validated_data)
        request_obj.refresh_from_db()
        return Response(request_detail_data(request_obj))


# --- Côté pro : demandes pour moi, devis ---------------------------------------------------------


class ProRequestPagination(CursorPagination):
    """Urgence puis ancienneté, par curseur : ``dispatch_rank`` est une clé unique triable."""

    ordering = "dispatch_rank"


class ProRequestListView(generics.ListAPIView):
    """Demandes pour moi : mon métier, mes zones, une place libre. Jamais le client."""

    permission_classes = [IsVerifiedPro]
    serializer_class = ProRequestSerializer
    pagination_class = ProRequestPagination

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ServiceRequest.objects.none()
        return requests_for_provider(provider=self.request.provider)

    @extend_schema(
        tags=["pro"],
        operation_id="pro_requests_list",
        responses={200: ProRequestSerializer(many=True), **ERRORS},
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)


class ProRequestDetailView(APIView):
    permission_classes = [IsVerifiedPro]

    @extend_schema(
        tags=["pro"],
        operation_id="pro_requests_retrieve",
        responses={200: ProRequestSerializer, **ERRORS},
    )
    def get(self, request: Request, public_id) -> Response:
        request_obj = request_for_provider(provider=request.provider, public_id=public_id)
        return Response(ProRequestSerializer(request_obj).data)


class ProQuoteCreateView(APIView):
    permission_classes = [IsVerifiedPro]

    @extend_schema(
        tags=["pro"],
        operation_id="pro_requests_quotes_create",
        parameters=[IDEMPOTENCY_PARAMETER],
        request=QuoteCreateSerializer,
        responses={
            201: ProQuoteSerializer,
            200: OpenApiResponse(ProQuoteSerializer, description="Rejeu : même devis"),
            409: OpenApiResponse(
                description=(
                    "quotes_full, quote_already_sent, pro_quote_limit, request_closed, "
                    "idempotency_key_reused, commission_debt_over_limit"
                )
            ),
            422: OpenApiResponse(
                description="quote_total_invalid, quote_details_required, slot_invalid"
            ),
            **ERRORS,
        },
    )
    def post(self, request: Request, public_id) -> Response:
        request_obj = request_for_provider(provider=request.provider, public_id=public_id)
        serializer = QuoteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        content = QuoteInput(
            kind=data["kind"],
            total_xof=data["total_xof"],
            lines=tuple(
                QuoteLineInput(line["kind"], line["amount_xof"], line["label"])
                for line in data["lines"]
            ),
            slot_day=data["slot_day"],
            slot_period=data["slot_period"],
            message=data["message"],
            visit_deductible=data["visit_deductible"],
        )
        result = submit_quote(
            provider=request.provider,
            request=request_obj,
            content=content,
            idempotency_key=idempotency_key(request),
        )
        quote = quote_for_provider(provider=request.provider, public_id=result.quote.public_id)
        code = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
        return Response(ProQuoteSerializer(quote).data, status=code)


class ProQuoteListView(generics.ListAPIView):
    permission_classes = [IsVerifiedPro]
    serializer_class = ProQuoteSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Quote.objects.none()
        return quotes_for_provider(provider=self.request.provider)

    @extend_schema(
        tags=["pro"],
        operation_id="pro_quotes_list",
        responses={200: ProQuoteSerializer(many=True), **ERRORS},
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)


class ProQuoteWithdrawView(APIView):
    permission_classes = [IsVerifiedPro, IsProOwner]

    @extend_schema(
        tags=["pro"],
        operation_id="pro_quotes_withdraw",
        request=None,
        responses={
            200: ProQuoteSerializer,
            409: OpenApiResponse(
                description="quote_not_available (seul un devis envoyé se retire)"
            ),
            **ERRORS,
        },
    )
    def post(self, request: Request, public_id) -> Response:
        quote = quote_for_provider(provider=request.provider, public_id=public_id)
        self.check_object_permissions(request, quote)
        withdraw_quote(quote=quote, provider=request.provider)
        quote = quote_for_provider(provider=request.provider, public_id=public_id)
        return Response(ProQuoteSerializer(quote).data)
