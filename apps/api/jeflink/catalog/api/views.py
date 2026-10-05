from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from jeflink.catalog.selectors import active_trade, active_trades
from jeflink.common.api.reference import PublicReferenceView
from jeflink.zones.api.serializers import CoveragePairSerializer
from jeflink.zones.selectors import coverage, open_zone_slugs

from .serializers import TradeDetailSerializer, TradeSummarySerializer


class TradeListView(PublicReferenceView):
    """Métiers actifs, par ``position`` (spec 002)."""

    @extend_schema(
        tags=["catalog"],
        operation_id="catalog_trades_list",
        responses=TradeSummarySerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        trades = active_trades()[: self.list_limit()]
        return self.cached_response(request, TradeSummarySerializer(trades, many=True).data)


class TradeDetailView(PublicReferenceView):
    """Un métier, ses services actifs et les zones où il est ouvert (pages SEO)."""

    @extend_schema(
        tags=["catalog"],
        operation_id="catalog_trade_retrieve",
        responses={
            200: TradeDetailSerializer,
            404: OpenApiResponse(description="trade_not_found"),
        },
    )
    def get(self, request: Request, slug: str) -> Response:
        trade = active_trade(slug)
        trade.open_zone_slugs = open_zone_slugs(trade)[: self.list_limit()]
        return self.cached_response(request, TradeDetailSerializer(trade).data)


class CoverageView(PublicReferenceView):
    """Paires métier et zone ouvertes : les pages du site et son sitemap (spec 006).

    Bornée par ``COVERAGE_LIST_MAX``, sans pagination.
    """

    @extend_schema(
        tags=["catalog"],
        operation_id="catalog_coverage_list",
        responses=CoveragePairSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        return self.cached_response(request, CoveragePairSerializer(coverage(), many=True).data)
