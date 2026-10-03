from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from jeflink.catalog.api.serializers import TradeSummarySerializer
from jeflink.common.api.reference import PublicReferenceView
from jeflink.zones.selectors import active_zone, active_zones, trades_in_zone

from .serializers import ZoneSerializer


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
