from django.db import connection
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    """Sonde de disponibilité : l'API répond et la base est joignable."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        operation_id="health",
        responses=inline_serializer("Health", fields={"status": serializers.CharField()}),
    )
    def get(self, request: Request) -> Response:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return Response({"status": "ok"})
