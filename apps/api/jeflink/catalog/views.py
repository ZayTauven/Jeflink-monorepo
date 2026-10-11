"""Lecture publique : métiers, quartiers, pros vérifiés et chiffres de la vitrine."""

from django.db.models import Avg
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import generics, serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from jeflink.accounts.models import ProProfile
from jeflink.jobs.models import Review, ServiceRequest

from .models import Trade, Zone


class TradeSerializer(serializers.ModelSerializer):
    pros_count = serializers.SerializerMethodField()

    class Meta:
        model = Trade
        fields = [
            "slug",
            "name",
            "tagline",
            "description",
            "services",
            "starting_price",
            "icon",
            "image",
            "pros_count",
        ]

    def get_pros_count(self, trade) -> int:
        return trade.pros.filter(is_verified=True).count()


class TradeRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Trade
        fields = ["slug", "name", "icon"]


class ZoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Zone
        fields = ["slug", "name", "city"]


class PublicProSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source="user_id")
    name = serializers.CharField(source="user.public_name")
    trades = TradeRefSerializer(many=True, read_only=True)
    zones = ZoneSerializer(many=True, read_only=True)
    rating = serializers.SerializerMethodField()
    missions_done = serializers.SerializerMethodField()

    class Meta:
        model = ProProfile
        fields = [
            "id",
            "name",
            "headline",
            "bio",
            "photo",
            "years_experience",
            "trades",
            "zones",
            "rating",
            "missions_done",
        ]

    def get_rating(self, profile) -> dict:
        return profile.rating()

    def get_missions_done(self, profile) -> int:
        return profile.user.missions.filter(status=ServiceRequest.Status.DONE).count()


class TradeList(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = TradeSerializer
    queryset = Trade.objects.filter(is_active=True)


class TradeDetail(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = TradeSerializer
    queryset = Trade.objects.filter(is_active=True)
    lookup_field = "slug"


class ZoneList(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = ZoneSerializer
    queryset = Zone.objects.filter(is_active=True)


@extend_schema(
    parameters=[
        OpenApiParameter("trade", str, description="slug du métier"),
        OpenApiParameter("zone", str, description="slug du quartier"),
    ]
)
class ProList(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = PublicProSerializer

    def get_queryset(self):
        qs = (
            ProProfile.objects.filter(is_verified=True, user__is_active=True)
            .select_related("user")
            .prefetch_related("trades", "zones")
            .order_by("-years_experience")
        )
        if trade := self.request.query_params.get("trade"):
            qs = qs.filter(trades__slug=trade)
        if zone := self.request.query_params.get("zone"):
            qs = qs.filter(zones__slug=zone)
        return qs.distinct()


class ProDetail(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = PublicProSerializer
    queryset = ProProfile.objects.filter(is_verified=True, user__is_active=True)
    lookup_field = "user_id"
    lookup_url_kwarg = "id"


@extend_schema(
    responses=inline_serializer(
        "Stats",
        {
            "pros": serializers.IntegerField(),
            "trades": serializers.IntegerField(),
            "zones": serializers.IntegerField(),
            "missions_done": serializers.IntegerField(),
            "average_rating": serializers.FloatField(allow_null=True),
        },
    )
)
@api_view(["GET"])
@permission_classes([AllowAny])
def stats(request):
    avg = Review.objects.aggregate(avg=Avg("rating"))["avg"]
    return Response(
        {
            "pros": ProProfile.objects.filter(is_verified=True).count(),
            "trades": Trade.objects.filter(is_active=True).count(),
            "zones": Zone.objects.filter(is_active=True).count(),
            "missions_done": ServiceRequest.objects.filter(status="done").count(),
            "average_rating": round(avg, 1) if avg else None,
        }
    )
