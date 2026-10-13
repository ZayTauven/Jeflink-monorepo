"""Lecture publique : métiers, quartiers, pros vérifiés et chiffres de la vitrine."""

from datetime import timedelta

from django.db.models import Avg, Q
from django.utils import timezone
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
        return trade.pros.filter(is_verified=True, user__is_active=True).count()


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


class PublicReviewSerializer(serializers.ModelSerializer):
    author = serializers.CharField(source="request.client.public_name")
    author_photo = serializers.CharField(source="request.client.photo")
    pro = serializers.CharField(source="request.pro.public_name")
    trade = serializers.CharField(source="request.trade.name")

    class Meta:
        model = Review
        fields = ["rating", "comment", "author", "author_photo", "pro", "trade", "created_at"]


class ReviewList(generics.ListAPIView):
    """Derniers avis avec commentaire (vitrine)."""

    permission_classes = [AllowAny]
    serializer_class = PublicReviewSerializer
    queryset = (
        Review.objects.exclude(comment="")
        .exclude(is_hidden=True)
        .select_related("request__client", "request__pro", "request__trade")
        .order_by("-created_at")[:6]
    )


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


@extend_schema(
    responses=inline_serializer(
        "SiteSettings",
        {
            "accepting_requests": serializers.BooleanField(),
            "closed_message": serializers.CharField(),
            "support_whatsapp": serializers.CharField(),
            "support_email": serializers.CharField(),
            "max_quotes": serializers.IntegerField(),
        },
    )
)
@api_view(["GET"])
@permission_classes([AllowAny])
def site(request):
    """Réglages publics de la plateforme (modifiés dans la console)."""
    from jeflink.console.models import PlatformSettings

    current = PlatformSettings.load()
    return Response(
        {
            "accepting_requests": current.accepting_requests,
            "closed_message": current.closed_message,
            "support_whatsapp": current.support_whatsapp,
            "support_email": current.support_email,
            "max_quotes": current.max_quotes,
            "jef_enabled": current.jef_enabled,
        }
    )


def _last_day(end):
    """Dernier jour valable d'une période qui finit à minuit (heure de Dakar)."""
    return timezone.localtime(end - timedelta(seconds=1)).date().isoformat() if end else None


def _terms(campaign) -> dict:
    """Conditions à afficher avec le bandeau : le client sait à quoi s'attendre avant de choisir."""
    coupon = campaign.coupon if campaign.coupon_id and campaign.coupon.is_active else None
    ends = [e for e in (campaign.ends_at, coupon and coupon.ends_at) if e]
    return {
        "min_amount": coupon.min_amount if coupon else None,
        "max_discount": coupon.max_discount if coupon else None,
        "first_order_only": bool(coupon and coupon.first_order_only),
        "ends_on": _last_day(min(ends)) if ends else None,
    }


@extend_schema(parameters=[OpenApiParameter("placement", str, enum=["home", "request"])])
@api_view(["GET"])
@permission_classes([AllowAny])
def campaigns(request):
    """Campagnes en cours pour un emplacement du site (accueil ou formulaire de demande)."""
    from jeflink.catalog.models import Campaign

    now = timezone.now()
    placement = request.query_params.get("placement", "home")
    places = [placement, Campaign.Placement.BOTH]
    live = (
        Campaign.objects.filter(is_active=True, placement__in=places)
        .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now))
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=now))
        .select_related("coupon")
        .order_by("-created_at")[:3]
    )
    return Response(
        [
            {
                "id": c.pk,
                "title": c.title,
                "message": c.message,
                "cta_label": c.cta_label,
                "cta_url": c.cta_url,
                "coupon_code": c.coupon.code if c.coupon_id and c.coupon.is_active else "",
                "terms": _terms(c),
            }
            for c in live
        ]
    )


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
    avg = Review.objects.filter(is_hidden=False).aggregate(avg=Avg("rating"))["avg"]
    return Response(
        {
            "pros": ProProfile.objects.filter(is_verified=True, user__is_active=True).count(),
            "trades": Trade.objects.filter(is_active=True).count(),
            "zones": Zone.objects.filter(is_active=True).count(),
            "missions_done": ServiceRequest.objects.filter(status="done").count(),
            "average_rating": round(avg, 1) if avg else None,
        }
    )
