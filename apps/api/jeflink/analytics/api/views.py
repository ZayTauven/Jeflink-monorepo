from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from jeflink.analytics.selectors import public_stats
from jeflink.catalog.selectors import active_trade
from jeflink.common.api.reference import PublicReferenceView
from jeflink.zones.selectors import active_zone

from .serializers import PublicStatsSerializer


class PublicStatsView(PublicReferenceView):
    """Preuves chiffrées et règles réelles pour le site public (spec 006), toutes à seuils."""

    @extend_schema(
        tags=["analytics"],
        operation_id="stats_retrieve",
        parameters=[
            OpenApiParameter("trade", str, description="Slug d'un métier actif."),
            OpenApiParameter("zone", str, description="Slug d'une zone active."),
        ],
        responses={
            200: PublicStatsSerializer,
            404: OpenApiResponse(description="trade_not_found, zone_not_found"),
        },
    )
    def get(self, request: Request) -> Response:
        trade_slug = request.query_params.get("trade")
        zone_slug = request.query_params.get("zone")
        trade = active_trade(trade_slug) if trade_slug else None
        zone = active_zone(zone_slug) if zone_slug else None
        return self.cached_response(request, PublicStatsSerializer(public_stats(trade, zone)).data)
