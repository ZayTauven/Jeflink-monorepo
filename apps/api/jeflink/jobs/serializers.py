from rest_framework import serializers

from jeflink.catalog.models import Trade, Zone
from jeflink.console.permissions import can

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
    pro_badges = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    with_code = serializers.SerializerMethodField()

    class Meta:
        model = Quote
        fields = [
            "id",
            "pro",
            "pro_headline",
            "pro_rating",
            "pro_badges",
            "amount",
            "message",
            "status",
            "status_label",
            "with_code",
            "created_at",
        ]

    def get_pro_rating(self, quote) -> dict:
        return quote.pro.pro_profile.rating()

    def get_pro_badges(self, quote) -> dict:
        """« Vérifié » (pièce d'identité acceptée par l'équipe) et « Pro confirmé » (gagné)."""
        profile = quote.pro.pro_profile
        # Vérifié = pièce d'identité acceptée (un pro vérifié avant cette règle n'a pas le badge).
        verified = profile.is_verified and profile.has_accepted_id()
        return {"verified": verified, "confirmed": profile.is_confirmed()}

    def get_with_code(self, quote) -> dict | None:
        """Pour le client, sur un devis à choisir : ce que donne le code promo de sa demande."""
        req, request = quote.request, self.context.get("request")
        if request is None or request.user.pk != req.client_id:
            return None
        if req.status != S.OPEN or quote.status != Quote.Status.PENDING:
            return None
        return services.code_preview(req, request.user, quote.amount)


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
    contact = serializers.SerializerMethodField()
    photos = serializers.SerializerMethodField()
    quotes = serializers.SerializerMethodField()
    quotes_count = serializers.IntegerField(source="quotes.count", read_only=True)
    quotes_max = serializers.SerializerMethodField()
    review = ReviewSerializer(read_only=True, allow_null=True)
    events = EventSerializer(many=True, read_only=True)
    dispute = serializers.SerializerMethodField()
    money = serializers.SerializerMethodField()
    jef = serializers.SerializerMethodField()
    cancellation = serializers.SerializerMethodField()
    promo_code = serializers.SerializerMethodField()
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
            "contact",
            "photos",
            "quotes",
            "quotes_count",
            "quotes_max",
            "review",
            "events",
            "dispute",
            "money",
            "jef",
            "cancellation",
            "promo_code",
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

    def get_quotes_max(self, req) -> int:
        return services.max_quotes()

    def get_contact_phone(self, req) -> str | None:
        """Le numéro de l'autre partie n'apparaît qu'une fois la mission réservée."""
        if req.status not in (S.BOOKED, S.CANCELLING, S.DONE):
            return None
        user = self._viewer
        if user.pk == req.client_id and req.pro:
            return req.pro.phone or None
        if user.pk == req.pro_id:
            return req.client.phone or None
        return None

    def get_contact(self, req) -> dict | None:
        """L'autre partie, une fois la mission réservée : comment et quand la joindre, et sa
        photo (celle du client n'est montrée qu'au pro choisi, jamais publiée)."""
        if req.status not in (S.BOOKED, S.CANCELLING, S.DONE) or req.pro is None:
            return None
        user = self._viewer
        if user.pk == req.client_id:
            other = req.pro
            photo = getattr(other, "pro_profile", None) and other.pro_profile.photo or other.photo
        elif user.pk == req.pro_id:
            other, photo = req.client, req.client.photo
        else:
            return None
        return {
            "name": other.public_name,
            "photo": photo,
            "prefers": other.get_contact_pref_display(),
            "hours": other.get_contact_hours_display(),
        }

    def get_photos(self, req) -> list[dict]:
        """Photos jointes par le client, pour qui peut les voir (services.can_see_media) ; le
        fichier se lit par /photos/<id>/file/."""
        if not services.can_see_media(self._viewer, req):
            return []
        return [
            {"id": m.pk, "created_at": m.created_at}
            for m in req.media.all()
            if m.kind == m.Kind.PHOTO
        ]

    def get_quotes(self, req) -> list:
        user = self._viewer
        quotes = req.quotes.select_related("pro__pro_profile")
        if user.pk != req.client_id and not user.is_staff:
            quotes = quotes.filter(pro=user)
        return QuoteSerializer(quotes, many=True, context=self.context).data

    def get_money(self, req) -> dict | None:
        """Montants de la mission réservée, pour le client et le pro concernés."""
        user = self._viewer
        if req.price is None or (user.pk not in (req.client_id, req.pro_id) and not user.is_staff):
            return None
        money = {
            "price": req.price,
            "discount": req.discount,
            "coupon": req.coupon.code if req.coupon_id else "",
            "client_pays": req.price - req.discount,
        }
        if user.pk == req.pro_id or can(user, "finance"):
            # Le pro touche le devis complet : le client paie price - discount sur place,
            # Jeflink compense la remise ; le pro doit la commission.
            money["commission"] = req.commission
            money["commission_rate"] = req.commission_rate
        return money

    def get_jef(self, req) -> dict | None:
        """Fiche préparée avec Jef, selon le lecteur : conseils pour le client, fiche pour le pro.

        Le titre et la description proposés par Jef ne sont pas renvoyés : seule compte la
        version que le client a publiée (il a pu la corriger).
        """
        session = getattr(req, "jef_session", None)
        if session is None or not session.brief:
            return None
        brief = session.brief
        out = {"mode": session.mode, "urgent": bool(brief.get("urgent"))}
        if self._viewer.pk == req.client_id:
            out["client_tips"] = brief.get("client_tips", [])
        else:
            for key in ("pro_summary", "pro_details", "pro_bring"):
                out[key] = brief.get(key, [] if key != "pro_summary" else "")
        return out

    def get_promo_code(self, req) -> str:
        """Code promo ajouté à la demande (le client seulement)."""
        return req.promo_code if self._viewer.pk == req.client_id else ""

    def get_cancellation(self, req) -> dict | None:
        """Motif de l'annulation, pour le client qui l'a donné (le pro voit seulement le statut)."""
        if not req.cancel_reason or req.status not in (S.CANCELLING, S.CANCELLED):
            return None
        if self._viewer.pk != req.client_id and not self._viewer.is_staff:
            return None
        return {
            "reason": req.cancel_reason,
            "reason_label": req.get_cancel_reason_display(),
            "note": req.cancel_note,
        }

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
                and req.quotes.count() < services.max_quotes()
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
    # Échange avec Jef dont la fiche accompagne la demande (facultatif).
    jef_session = serializers.IntegerField(
        required=False, allow_null=True, write_only=True, min_value=1, max_value=2**31 - 1
    )

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
            "jef_session",
            "promo_code",
            "save_address",
        ]
        extra_kwargs = {"promo_code": {"required": False, "allow_blank": True}}

    # Nom sous lequel enregistrer ce quartier + repère dans « Mes adresses » (facultatif).
    save_address = serializers.CharField(
        max_length=40, required=False, allow_blank=True, write_only=True, default=""
    )


class QuoteCreateSerializer(serializers.Serializer):
    amount = serializers.IntegerField(min_value=1, max_value=10_000_000)
    message = serializers.CharField(required=False, allow_blank=True, max_length=1000)


class AcceptSerializer(serializers.Serializer):
    quote_id = serializers.IntegerField()
    coupon = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")


class DisputeCreateSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(choices=Dispute.Reason.choices)
    description = serializers.CharField(max_length=2000)


class PromoCodeSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=20, allow_blank=True)


class CancelSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(choices=ServiceRequest.CancelReason.choices)
    note = serializers.CharField(required=False, allow_blank=True, max_length=300, default="")


class ReviewCreateSerializer(serializers.Serializer):
    rating = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(required=False, allow_blank=True, max_length=1000)
