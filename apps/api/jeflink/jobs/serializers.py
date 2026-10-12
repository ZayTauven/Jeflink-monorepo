from rest_framework import serializers

from jeflink.catalog.models import Trade, Zone

from . import services
from .models import Dispute, Quote, RequestEvent, Review, ServiceRequest

S = ServiceRequest.Status


class PersonSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField(source="public_name")


class QuoteSerializer(serializers.ModelSerializer):
    pro = PersonSerializer(read_only=True)
    pro_headline = serializers.CharField(source="pro.pro_profile.headline", read_only=True)
    pro_rating = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Quote
        fields = [
            "id",
            "pro",
            "pro_headline",
            "pro_rating",
            "amount",
            "message",
            "status",
            "status_label",
            "created_at",
        ]

    def get_pro_rating(self, quote) -> dict:
        return quote.pro.pro_profile.rating()


class ReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = ["rating", "comment", "created_at"]


class EventSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = RequestEvent
        fields = ["status", "status_label", "note", "created_at"]


class DisputeSerializer(serializers.ModelSerializer):
    """Litige vu par le client et le pro de la mission (sans les échanges internes)."""

    reason_label = serializers.CharField(source="get_reason_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Dispute
        fields = [
            "id",
            "reason",
            "reason_label",
            "description",
            "status",
            "status_label",
            "resolution",
            "created_at",
            "closed_at",
        ]


class RequestSerializer(serializers.ModelSerializer):
    trade = serializers.SerializerMethodField()
    zone = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    client = PersonSerializer(read_only=True)
    pro = PersonSerializer(read_only=True, allow_null=True)
    contact_phone = serializers.SerializerMethodField()
    quotes = serializers.SerializerMethodField()
    quotes_count = serializers.IntegerField(source="quotes.count", read_only=True)
    review = ReviewSerializer(read_only=True, allow_null=True)
    events = EventSerializer(many=True, read_only=True)
    dispute = serializers.SerializerMethodField()
    actions = serializers.SerializerMethodField()

    class Meta:
        model = ServiceRequest
        fields = [
            "id",
            "title",
            "description",
            "landmark",
            "preferred_date",
            "is_urgent",
            "status",
            "status_label",
            "trade",
            "zone",
            "client",
            "pro",
            "contact_phone",
            "quotes",
            "quotes_count",
            "review",
            "events",
            "dispute",
            "actions",
            "created_at",
        ]

    @property
    def _viewer(self):
        return self.context["request"].user

    def get_trade(self, req) -> dict:
        return {"slug": req.trade.slug, "name": req.trade.name, "icon": req.trade.icon}

    def get_zone(self, req) -> dict:
        return {"slug": req.zone.slug, "name": req.zone.name}

    def get_contact_phone(self, req) -> str | None:
        """Le numéro de l'autre partie n'apparaît qu'une fois la mission réservée."""
        if req.status not in (S.BOOKED, S.DONE):
            return None
        user = self._viewer
        if user.pk == req.client_id and req.pro:
            return req.pro.phone or None
        if user.pk == req.pro_id:
            return req.client.phone or None
        return None

    def get_quotes(self, req) -> list:
        user = self._viewer
        quotes = req.quotes.select_related("pro__pro_profile")
        if user.pk != req.client_id and not user.is_staff:
            quotes = quotes.filter(pro=user)
        return QuoteSerializer(quotes, many=True, context=self.context).data

    def _dispute(self, req):
        return req.disputes.order_by("-created_at").first()

    def get_dispute(self, req) -> dict | None:
        """Le dernier litige de la mission, pour le client et le pro concernés."""
        user = self._viewer
        if user.pk not in (req.client_id, req.pro_id) and not user.is_staff:
            return None
        dispute = self._dispute(req)
        return None if dispute is None else DisputeSerializer(dispute).data

    def get_actions(self, req) -> list[str]:
        user = self._viewer
        actions = []
        if user.pk in (req.client_id, req.pro_id) and req.status in (S.BOOKED, S.DONE):
            dispute = self._dispute(req)
            if dispute is None or dispute.is_closed:
                actions.append("report")
        if user.pk == req.client_id:
            if req.status == S.OPEN and req.quotes.exists():
                actions.append("accept")
            if req.status in (S.OPEN, S.BOOKED):
                actions.append("cancel")
            if req.status == S.BOOKED:
                actions.append("complete")
            if req.status == S.DONE and not hasattr(req, "review"):
                actions.append("review")
        elif user.is_pro:
            if (
                req.status == S.OPEN
                and not req.quotes.filter(pro=user).exists()
                and req.quotes.count() < services.MAX_QUOTES
                and getattr(user, "pro_profile", None) is not None
                and user.pro_profile.is_verified
            ):
                actions.append("quote")
            if req.status == S.BOOKED and user.pk == req.pro_id:
                actions.append("complete")
        return actions


class RequestCreateSerializer(serializers.ModelSerializer):
    trade = serializers.SlugRelatedField(slug_field="slug", queryset=Trade.objects.all())
    zone = serializers.SlugRelatedField(slug_field="slug", queryset=Zone.objects.all())

    class Meta:
        model = ServiceRequest
        fields = [
            "trade",
            "zone",
            "title",
            "description",
            "landmark",
            "preferred_date",
            "is_urgent",
        ]


class QuoteCreateSerializer(serializers.Serializer):
    amount = serializers.IntegerField(min_value=1, max_value=10_000_000)
    message = serializers.CharField(required=False, allow_blank=True, max_length=1000)


class AcceptSerializer(serializers.Serializer):
    quote_id = serializers.IntegerField()


class DisputeCreateSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(choices=Dispute.Reason.choices)
    description = serializers.CharField(max_length=2000)


class ReviewCreateSerializer(serializers.Serializer):
    rating = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(required=False, allow_blank=True, max_length=1000)
