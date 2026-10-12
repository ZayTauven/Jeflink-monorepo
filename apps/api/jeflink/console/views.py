"""API de la console d'administration : réservée à l'équipe Jeflink (comptes ``is_staff``)."""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from . import stats

PERIODS = {7, 30, 90}


@extend_schema(
    parameters=[OpenApiParameter("days", int, description="Période : 7, 30 ou 90 jours")],
    responses=OpenApiTypes.OBJECT,
)
@api_view(["GET"])
@permission_classes([IsAdminUser])
def overview(request):
    """Tableau de bord : indicateurs de la période et de la précédente, séries, alertes."""
    try:
        days = int(request.query_params.get("days", 30))
    except ValueError:
        days = 30
    return Response(stats.overview(days if days in PERIODS else 30))


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([IsAdminUser])
def badges(request):
    """Compteurs du menu : pros à vérifier, demandes sans devis, messages non traités."""
    return Response(stats.badges())
