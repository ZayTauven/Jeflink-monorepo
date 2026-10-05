from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from jeflink.catalog.api.serializers import TradeSummarySerializer
from jeflink.catalog.selectors import active_trade
from jeflink.common.api.reference import PublicReferenceView
from jeflink.zones.selectors import (
    active_zone,
    active_zones,
    is_indexable,
    nearby_zones,
    trades_in_zone,
)

from .serializers import ZoneDetailSerializer, ZoneSerializer


class ZoneListView(PublicReferenceView):
    """Zones actives de villes actives, par popularité puis nom (spec 002)."""

    @extend_schema(
        tags=["zones"],
        operation_id="zones_list",
        parameters=[OpenApiParameter("city", str, description="Slug de la ville (ex. dakar).")],
        responses=ZoneSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        zones = active_zones(city_slug=request.query_params.get("city") or None)
        return self.cached_response(
            request, ZoneSerializer(zones[: self.list_limit()], many=True).data
        )


class ZoneDetailView(PublicReferenceView):
    """Une zone pour sa page métier et quartier : textes, indexation, quartiers voisins (spec 006).

    ``?trade=`` limite les voisins aux zones où ce métier est ouvert. La distance sert au tri
    seulement : ni position, ni rayon, ni contour dans la réponse.
    """

    @extend_schema(
        tags=["zones"],
        operation_id="zone_retrieve",
        parameters=[
            OpenApiParameter(
                "trade", str, description="Slug d'un métier : voisins où il est ouvert."
            )
        ],
        responses={
            200: ZoneDetailSerializer,
            404: OpenApiResponse(description="zone_not_found, trade_not_found"),
        },
    )
    def get(self, request: Request, slug: str) -> Response:
        zone = active_zone(slug)
        trade_slug = request.query_params.get("trade")
        trade = active_trade(trade_slug) if trade_slug else None
        zone.nearby_zones = nearby_zones(zone, trade=trade)
        zone.indexable = is_indexable(zone)
        return self.cached_response(request, ZoneDetailSerializer(zone).data)


class ZoneTradesView(PublicReferenceView):
    """Métiers ouverts dans une zone, sous la même forme que la liste des métiers."""

    @extend_schema(
        tags=["zones"],
        operation_id="zone_trades_list",
        responses={
            200: TradeSummarySerializer(many=True),
            404: OpenApiResponse(description="zone_not_found"),
        },
    )
    def get(self, request: Request, slug: str) -> Response:
        trades = trades_in_zone(active_zone(slug))[: self.list_limit()]
        return self.cached_response(request, TradeSummarySerializer(trades, many=True).data)
