"""Portefeuille du pro (spec 005, tâche 8) : résumé, historique et règlements.

Gérant seulement (``HasOwnerRole``) ; une fiche suspendue lit son portefeuille et règle sa dette.
Un objet d'un autre pro répond ``404``. Ces vues vivent dans ``payments`` : elles montrent les
canaux et appellent ses services, et ``payments`` peut lire ``wallet`` (jamais l'inverse).
"""

from django.conf import settings
from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from jeflink.accounts.permissions import HasOwnerRole
from jeflink.common.api.idempotency import IDEMPOTENCY_PARAMETER, idempotency_key
from jeflink.common.errors import DomainError
from jeflink.providers.selectors import provider_for_owner
from jeflink.requests.api.serializers import ApiErrorSerializer
from jeflink.wallet.selectors import (
    commission_for_transaction,
    entries_for_provider,
    entry_for_provider,
    next_rate_for,
    provider_wallet,
    rate_for,
    reversals_of,
)
from jeflink.wallet.services import transaction_total

from .. import services
from ..models import PaymentIntent
from ..selectors import channel_by_slug, channels_for_pro, intent_for_provider, intents_for_provider
from .serializers import (
    SettlementCorrectSerializer,
    SettlementCreateSerializer,
    SettlementSerializer,
    WalletEntryDetailSerializer,
    WalletEntrySerializer,
    WalletSummarySerializer,
)

ERRORS = {
    401: OpenApiResponse(description="not_authenticated"),
    403: OpenApiResponse(description="profile_incomplete, role_required"),
    404: OpenApiResponse(description="not_found"),
}


def error(description: str) -> OpenApiResponse:
    return OpenApiResponse(ApiErrorSerializer, description=description)


def owned_provider(request: Request):
    """La fiche du gérant, suspendue comprise ; 404 s'il n'en a pas."""
    provider = provider_for_owner(request.user)
    if provider is None:
        raise DomainError("not_found", status=404)
    return provider


def _rates(provider, now) -> list[dict]:
    rates = []
    for trade in sorted(provider.trades.all(), key=lambda t: t.slug):
        current = rate_for(trade=trade, at=now)
        if current is None:
            continue
        upcoming = next_rate_for(trade=trade, at=now)
        rates.append(
            {
                "trade_slug": trade.slug,
                "rate_bps": current.rate_bps,
                "cap_xof": current.cap_xof,
                "next": None
                if upcoming is None
                else {
                    "rate_bps": upcoming.rate_bps,
                    "cap_xof": upcoming.cap_xof,
                    "valid_from": upcoming.valid_from,
                },
            }
        )
    return rates


class WalletSummaryView(APIView):
    permission_classes = [HasOwnerRole]

    @extend_schema(
        tags=["wallet"],
        operation_id="pro_wallet_retrieve",
        responses={200: WalletSummarySerializer, **ERRORS},
    )
    def get(self, request: Request) -> Response:
        provider = owned_provider(request)
        wallet = provider_wallet(provider)
        data = {
            "due_xof": wallet.due_xof,
            "credit_xof": wallet.credit_xof,
            "pending_xof": wallet.pending_xof,
            "effective_due_xof": wallet.effective_due_xof,
            "state": str(wallet.state),
            "alert_threshold_xof": settings.WALLET_DEBT_ALERT_XOF,
            "block_threshold_xof": settings.WALLET_DEBT_BLOCK_XOF,
            "rates": _rates(provider, timezone.now()),
            "channels": list(channels_for_pro()),
        }
        return Response(WalletSummarySerializer(data).data)


class WalletEntryListView(generics.ListAPIView):
    permission_classes = [HasOwnerRole]
    serializer_class = WalletEntrySerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return entries_for_provider(None).none()
        return entries_for_provider(owned_provider(self.request))

    @extend_schema(
        tags=["wallet"],
        operation_id="pro_wallet_entries_list",
        responses={200: WalletEntrySerializer(many=True), **ERRORS},
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)


class WalletEntryDetailView(APIView):
    permission_classes = [HasOwnerRole]

    @extend_schema(
        tags=["wallet"],
        operation_id="pro_wallet_entries_retrieve",
        responses={200: WalletEntryDetailSerializer, **ERRORS},
    )
    def get(self, request: Request, public_id) -> Response:
        entry = entry_for_provider(provider=owned_provider(request), public_id=public_id)
        txn = entry.transaction
        entry.commission = commission_for_transaction(txn)
        entry.reversals = [
            {
                "public_id": r.public_id,
                "amount_xof": transaction_total(r),
                "reason_code": r.reason_code,
                "created_at": r.created_at,
            }
            for r in reversals_of(txn)
        ]
        return Response(WalletEntryDetailSerializer(entry).data)


class SettlementListCreateView(generics.ListAPIView):
    permission_classes = [HasOwnerRole]
    serializer_class = SettlementSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return PaymentIntent.objects.none()
        return intents_for_provider(owned_provider(self.request))

    @extend_schema(
        tags=["wallet"],
        operation_id="pro_wallet_settlements_list",
        responses={200: SettlementSerializer(many=True), **ERRORS},
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)

    @extend_schema(
        tags=["wallet"],
        operation_id="pro_wallet_settlements_create",
        parameters=[IDEMPOTENCY_PARAMETER],
        request=SettlementCreateSerializer,
        responses={
            201: SettlementSerializer,
            200: OpenApiResponse(SettlementSerializer, description="Rejeu : même déclaration"),
            409: error(
                "nothing_due, settlement_reference_used, settlement_pending_limit, "
                "idempotency_key_reused"
            ),
            422: error(
                "settlement_exceeds_due (payable_xof), settlement_amount_invalid, "
                "settlement_reference_invalid, paid_at_invalid, payer_last4_invalid, "
                "channel_inactive"
            ),
            429: error("settlement_rate_limited"),
            **ERRORS,
        },
    )
    def post(self, request: Request) -> Response:
        provider = owned_provider(request)
        serializer = SettlementCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = services.declare_settlement(
            provider=provider,
            actor=request.user,
            channel=channel_by_slug(data["channel"]),
            amount_xof=data["amount_xof"],
            reference=data["reference"],
            paid_at=data["paid_at"],
            payer_last4=data["payer_last4"],
            idempotency_key=idempotency_key(request),
        )
        intent = intent_for_provider(provider=provider, public_id=result.intent.public_id)
        code = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
        return Response(SettlementSerializer(intent).data, status=code)


class SettlementCorrectView(APIView):
    permission_classes = [HasOwnerRole]

    @extend_schema(
        tags=["wallet"],
        operation_id="pro_wallet_settlements_correct",
        request=SettlementCorrectSerializer,
        responses={
            200: SettlementSerializer,
            409: error("settlement_not_correctable, settlement_reference_used"),
            422: error(
                "settlement_exceeds_due, settlement_amount_invalid, settlement_reference_invalid, "
                "paid_at_invalid, payer_last4_invalid, channel_inactive"
            ),
            **ERRORS,
        },
    )
    def post(self, request: Request, public_id) -> Response:
        provider = owned_provider(request)
        intent = intent_for_provider(provider=provider, public_id=public_id)
        serializer = SettlementCorrectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.correct_settlement(intent=intent, actor=request.user, **serializer.validated_data)
        intent = intent_for_provider(provider=provider, public_id=public_id)
        return Response(SettlementSerializer(intent).data)


class SettlementCancelView(APIView):
    permission_classes = [HasOwnerRole]

    @extend_schema(
        tags=["wallet"],
        operation_id="pro_wallet_settlements_cancel",
        request=None,
        responses={
            200: SettlementSerializer,
            409: error("settlement_not_pending, settlement_not_cancellable"),
            **ERRORS,
        },
    )
    def post(self, request: Request, public_id) -> Response:
        provider = owned_provider(request)
        intent = intent_for_provider(provider=provider, public_id=public_id)
        services.cancel_settlement(intent=intent, actor=request.user)
        intent = intent_for_provider(provider=provider, public_id=public_id)
        return Response(SettlementSerializer(intent).data)
