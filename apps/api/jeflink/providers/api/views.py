"""API du pro : sa fiche (spec 003)."""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from jeflink.accounts.permissions import HasOwnerRole
from jeflink.common.errors import DomainError
from jeflink.providers.models import Provider
from jeflink.providers.selectors import provider_for_owner
from jeflink.requests.api.refs import TradeRefSerializer, ZoneRefSerializer


class ProProviderSerializer(serializers.ModelSerializer):
    """Ma fiche : statut de vérification, métiers et zones."""

    trades = TradeRefSerializer(many=True)
    zones = ZoneRefSerializer(many=True)

    class Meta:
        model = Provider
        fields = ["public_id", "business_name", "status", "trades", "zones"]
        read_only_fields = fields


class ProMeView(APIView):
    permission_classes = [HasOwnerRole]

    @extend_schema(
        tags=["pro"],
        operation_id="pro_me_retrieve",
        responses={
            200: ProProviderSerializer,
            403: OpenApiResponse(description="role_required"),
            404: OpenApiResponse(description="not_found (aucune fiche)"),
        },
    )
    def get(self, request: Request) -> Response:
        provider = provider_for_owner(request.user)
        if provider is None:
            raise DomainError("not_found", status=404)
        return Response(ProProviderSerializer(provider).data)
