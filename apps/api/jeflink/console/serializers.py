"""Sérialiseurs de la console : l'équipe voit noms complets, emails et téléphones (support)."""

import re
from datetime import datetime, time, timedelta

from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers

from jeflink.accounts.models import ContactMessage, ProProfile, User, normalize_phone
from jeflink.catalog.models import Campaign, Trade, Zone
from jeflink.jef.models import JefSession
from jeflink.jobs import services as jobs_services
from jeflink.jobs.models import Coupon, Dispute, Quote, RequestEvent, Review, ServiceRequest

from .models import AuditLog, PlatformSettings, ProSettlement


def person(user: User | None) -> dict | None:
    if user is None:
        return None
    return {
        "id": user.pk,
        "name": user.get_full_name() or user.email,
        "email": user.email,
        "phone": user.phone,
        "role": user.role,
    }


def short(user: User | None) -> dict | None:
    return None if user is None else {"id": user.pk, "name": user.get_full_name() or user.email}


# --- Demandes ------------------------------------------------------------------------------------


class RequestRowSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display")
    trade = serializers.SerializerMethodField()
    zone = serializers.SerializerMethodField()
    client = serializers.SerializerMethodField()
    pro = serializers.SerializerMethodField()
    quotes_count = serializers.IntegerField(source="n_quotes", default=0)
    quotes_max = serializers.SerializerMethodField()
    amount = serializers.IntegerField(source="accepted_amount", allow_null=True, default=None)
    open_disputes = serializers.IntegerField(source="n_open_disputes", default=0)

    class Meta:
        model = ServiceRequest
        fields = [
            "id",
            "title",
            "status",
            "status_label",
            "is_urgent",
            "trade",
            "zone",
            "client",
            "pro",
            "quotes_count",
            "quotes_max",
            "amount",
            "open_disputes",
            "created_at",
            "updated_at",
        ]

    def get_quotes_max(self, req) -> int:
        if "quotes_max" not in self.context:  # une lecture des réglages par liste
            self.context["quotes_max"] = jobs_services.max_quotes()
        return self.context["quotes_max"]

    def get_trade(self, req) -> dict:
        return {"slug": req.trade.slug, "name": req.trade.name, "icon": req.trade.icon}

    def get_zone(self, req) -> dict:
        return {"slug": req.zone.slug, "name": req.zone.name}

    def get_client(self, req) -> dict:
        return short(req.client)

    def get_pro(self, req) -> dict | None:
        return short(req.pro)


class QuoteRowSerializer(serializers.ModelSerializer):
    pro = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display")

    class Meta:
        model = Quote
        fields = ["id", "pro", "amount", "message", "status", "status_label", "created_at"]

    def get_pro(self, quote) -> dict:
        return short(quote.pro)


class EventRowSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display")
    actor = serializers.SerializerMethodField()

    class Meta:
        model = RequestEvent
        fields = ["id", "status", "status_label", "note", "actor", "created_at"]

    def get_actor(self, event) -> dict | None:
        return short(event.actor)


class DisputeSerializer(serializers.ModelSerializer):
    reason_label = serializers.CharField(source="get_reason_display")
    status_label = serializers.CharField(source="get_status_display")
    request = serializers.SerializerMethodField()
    opened_by = serializers.SerializerMethodField()
    handled_by = serializers.SerializerMethodField()
    client = serializers.SerializerMethodField()
    pro = serializers.SerializerMethodField()

    class Meta:
        model = Dispute
        fields = [
            "id",
            "request",
            "reason",
            "reason_label",
            "description",
            "status",
            "status_label",
            "resolution",
            "opened_by",
            "handled_by",
            "client",
            "pro",
            "created_at",
            "closed_at",
        ]

    def get_request(self, d) -> dict:
        return {"id": d.request_id, "title": d.request.title, "status": d.request.status}

    def get_opened_by(self, d) -> dict:
        return person(d.opened_by)

    def get_handled_by(self, d) -> dict | None:
        return short(d.handled_by)

    def get_client(self, d) -> dict:
        return person(d.request.client)

    def get_pro(self, d) -> dict | None:
        return person(d.request.pro)


class ReviewRowSerializer(serializers.ModelSerializer):
    request = serializers.SerializerMethodField()
    client = serializers.SerializerMethodField()
    pro = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = [
            "id",
            "request",
            "rating",
            "comment",
            "is_hidden",
            "hidden_reason",
            "client",
            "pro",
            "created_at",
        ]

    def get_request(self, r) -> dict:
        return {"id": r.request_id, "title": r.request.title, "trade": r.request.trade.name}

    def get_client(self, r) -> dict:
        return short(r.request.client)

    def get_pro(self, r) -> dict | None:
        return short(r.request.pro)


class RequestDetailSerializer(RequestRowSerializer):
    client = serializers.SerializerMethodField()
    pro = serializers.SerializerMethodField()
    quotes = QuoteRowSerializer(many=True)
    events = EventRowSerializer(many=True)
    review = serializers.SerializerMethodField()
    disputes = DisputeSerializer(many=True)
    can_cancel = serializers.SerializerMethodField()
    can_open_dispute = serializers.SerializerMethodField()

    class Meta(RequestRowSerializer.Meta):
        fields = [
            *RequestRowSerializer.Meta.fields,
            "description",
            "landmark",
            "preferred_date",
            "quotes",
            "events",
            "review",
            "disputes",
            "staff_note",
            "can_cancel",
            "can_open_dispute",
        ]

    def get_client(self, req) -> dict:
        return person(req.client)

    def get_pro(self, req) -> dict | None:
        return person(req.pro)

    def get_review(self, req) -> dict | None:
        review = getattr(req, "review", None)
        return None if review is None else ReviewRowSerializer(review).data

    def get_can_cancel(self, req) -> bool:
        return req.status in (ServiceRequest.Status.OPEN, ServiceRequest.Status.BOOKED)

    def get_can_open_dispute(self, req) -> bool:
        return req.status in (
            ServiceRequest.Status.BOOKED,
            ServiceRequest.Status.DONE,
        ) and not any(not d.is_closed for d in req.disputes.all())


# --- Pros et clients -----------------------------------------------------------------------------


class AccountSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source="pk")
    name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "name",
            "email",
            "phone",
            "photo",
            "is_active",
            "suspension_reason",
            "date_joined",
            "last_login",
        ]

    def get_name(self, user) -> str:
        return user.get_full_name() or user.email


class ProRowSerializer(serializers.ModelSerializer):
    account = serializers.SerializerMethodField()
    trades = serializers.SerializerMethodField()
    zones = serializers.SerializerMethodField()
    missions_done = serializers.IntegerField(source="n_done", default=0)
    rating = serializers.SerializerMethodField()

    class Meta:
        model = ProProfile
        fields = [
            "account",
            "headline",
            "photo",
            "years_experience",
            "trades",
            "zones",
            "is_verified",
            "verified_at",
            "verification_note",
            "missions_done",
            "rating",
        ]

    def get_account(self, profile) -> dict:
        return AccountSerializer(profile.user).data

    def get_trades(self, profile) -> list[str]:
        return [t.name for t in profile.trades.all()]

    def get_zones(self, profile) -> list[str]:
        return [z.name for z in profile.zones.all()]

    def get_rating(self, profile) -> dict:
        return profile.rating()


class ClientRowSerializer(AccountSerializer):
    requests_count = serializers.IntegerField(source="n_requests", default=0)
    spent = serializers.IntegerField(default=0)
    last_request_at = serializers.DateTimeField(allow_null=True, default=None)

    class Meta(AccountSerializer.Meta):
        fields = [*AccountSerializer.Meta.fields, "requests_count", "spent", "last_request_at"]


# --- Messages et journal -------------------------------------------------------------------------


class ContactRowSerializer(serializers.ModelSerializer):
    handled_by = serializers.SerializerMethodField()

    class Meta:
        model = ContactMessage
        fields = [
            "id",
            "name",
            "email",
            "message",
            "is_handled",
            "handled_at",
            "handled_by",
            "created_at",
        ]

    def get_handled_by(self, m) -> dict | None:
        return short(m.handled_by)


class AuditRowSerializer(serializers.ModelSerializer):
    action_label = serializers.CharField(source="get_action_display")
    actor = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "action",
            "action_label",
            "actor",
            "target_type",
            "target_id",
            "target_label",
            "details",
            "created_at",
        ]

    def get_actor(self, log) -> dict | None:
        return short(log.actor)


# --- Entrées des actions -------------------------------------------------------------------------


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=300, allow_blank=True)


class NoteSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=2000, allow_blank=True)


class DisputeOpenSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(choices=Dispute.Reason.choices)
    description = serializers.CharField(max_length=2000)


class DisputeUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=[c for c in Dispute.Status.choices if c[0] != Dispute.Status.OPEN]
    )
    resolution = serializers.CharField(max_length=2000, required=False, allow_blank=True)


# --- Lot 2 : catalogue, réglages, équipe ---------------------------------------------------------


class TradeConsoleSerializer(serializers.ModelSerializer):
    pros_verified = serializers.IntegerField(source="n_pros", default=0)
    requests_30d = serializers.IntegerField(source="n_recent", default=0)
    requests_total = serializers.IntegerField(source="n_total", default=0)

    class Meta:
        model = Trade
        fields = [
            "id",
            "slug",
            "name",
            "tagline",
            "description",
            "services",
            "starting_price",
            "icon",
            "image",
            "position",
            "is_active",
            "pros_verified",
            "requests_30d",
            "requests_total",
        ]


class TradeInputSerializer(serializers.Serializer):
    """Saisie d'un métier depuis la console (formulaire : champs texte)."""

    name = serializers.CharField(max_length=80)
    tagline = serializers.CharField(max_length=180, required=False, allow_blank=True, default="")
    description = serializers.CharField(required=False, allow_blank=True, default="")
    services = serializers.CharField(required=False, allow_blank=True, default="")
    starting_price = serializers.CharField(required=False, allow_blank=True, default="")
    icon = serializers.RegexField(
        r"^(bi-[a-z0-9-]+)?$", required=False, allow_blank=True, default="", max_length=40
    )
    image = serializers.RegexField(
        r"^(/images/(?!.*\.\.)[\w/.-]+)?$",
        required=False,
        allow_blank=True,
        default="",
        max_length=200,
    )
    position = serializers.IntegerField(min_value=0, max_value=999, default=0)
    is_active = serializers.BooleanField(default=True)

    def validate_services(self, value) -> list[str]:
        """Une prestation par ligne → liste JSON, sans lignes vides ni doublons."""
        seen: list[str] = []
        for line in value.splitlines():
            item = line.strip(" -•\t")
            if item and item not in seen:
                seen.append(item[:80])
        return seen[:20]

    def validate_starting_price(self, value) -> int | None:
        """« 5 000 », « 5000 F CFA » → 5000 (entier F CFA) ; vide → pas de prix affiché."""
        digits = "".join(ch for ch in value if "0" <= ch <= "9")
        if not digits:
            return None
        price = int(digits)
        if price > 10_000_000:
            raise serializers.ValidationError("Prix trop élevé.")
        return price


class ZoneConsoleSerializer(serializers.ModelSerializer):
    pros_count = serializers.SerializerMethodField()
    requests_30d = serializers.IntegerField(source="n_recent", default=0)

    class Meta:
        model = Zone
        fields = [
            "id",
            "slug",
            "name",
            "city",
            "position",
            "is_active",
            "pros_count",
            "requests_30d",
        ]

    def get_pros_count(self, zone) -> int:
        """Pros vérifiés qui couvrent le quartier : l'ayant choisi, ou allant partout."""
        if "everywhere" not in self.context:
            self.context["everywhere"] = ProProfile.objects.filter(
                is_verified=True, user__is_active=True, zones=None
            ).count()
        return getattr(zone, "n_pros", 0) + self.context["everywhere"]


class ZoneInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=80)
    city = serializers.CharField(max_length=80, default="Dakar")
    position = serializers.IntegerField(min_value=0, max_value=999, default=0)
    is_active = serializers.BooleanField(default=True)


class SettingsSerializer(serializers.ModelSerializer):
    updated_by = serializers.SerializerMethodField()
    # Saisie libre (« 77 123 45 67 ») normalisée en E.164 par validate_support_whatsapp.
    support_whatsapp = serializers.CharField(max_length=20, allow_blank=True, required=False)

    class Meta:
        model = PlatformSettings
        fields = [
            "max_quotes",
            "stale_after_hours",
            "accepting_requests",
            "closed_message",
            "support_whatsapp",
            "support_email",
            "jef_enabled",
            "updated_at",
            "updated_by",
        ]
        read_only_fields = ["updated_at", "updated_by"]

    def get_updated_by(self, obj) -> dict | None:
        return short(obj.updated_by)

    def validate_support_whatsapp(self, value: str) -> str:
        if not value.strip():
            return ""
        try:
            return normalize_phone(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages[0]) from exc


class MemberSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    role = serializers.CharField(source="console_role")
    role_label = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "name",
            "email",
            "role",
            "role_label",
            "is_active",
            "is_superuser",
            "last_login",
            "date_joined",
        ]

    def get_name(self, user) -> str:
        return user.get_full_name() or user.email

    def get_role_label(self, user) -> str:
        return User.StaffRole(user.console_role).label


class MemberCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    role = serializers.ChoiceField(choices=User.StaffRole.choices)
    password = serializers.CharField(min_length=10, max_length=128, write_only=True)

    def validate(self, attrs):
        # Comparé à l'email et au nom : refuse un mot de passe qui ressemble à l'identité.
        candidate = User(
            email=attrs["email"],
            first_name=attrs["first_name"],
            last_name=attrs.get("last_name", ""),
        )
        try:
            password_validation.validate_password(attrs["password"], candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": exc.messages[0]}) from exc
        return attrs


class RoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=User.StaffRole.choices)


# --- Lot 3 : marketing et finances ---------------------------------------------------------------


def _day_start(d):
    return timezone.make_aware(datetime.combine(d, time.min))


def _local_date(dt):
    return timezone.localdate(dt).isoformat() if dt else None


class PeriodFields(serializers.Serializer):
    """Dates saisies (jour) → instants : début à 0 h, fin à minuit le lendemain (heure de Dakar)."""

    starts_on = serializers.DateField(required=False, allow_null=True, default=None)
    ends_on = serializers.DateField(required=False, allow_null=True, default=None)

    def to_internal_value(self, data):
        data = data.copy() if hasattr(data, "copy") else dict(data)
        for key in ("starts_on", "ends_on"):
            if data.get(key) == "":
                data[key] = None
        return super().to_internal_value(data)

    def validate(self, attrs):
        start, end = attrs.pop("starts_on", None), attrs.pop("ends_on", None)
        if start and end and end < start:
            raise serializers.ValidationError({"ends_on": "La fin doit suivre le début."})
        attrs["starts_at"] = _day_start(start) if start else None
        attrs["ends_at"] = _day_start(end + timedelta(days=1)) if end else None
        return attrs


def _optional_int(value: str, maximum: int, field: str) -> int | None:
    # Chiffres et espaces seulement : « 7,5 » ou « -3000 » sont refusés, pas recollés.
    text = str(value or "").strip()
    if not text:
        return None
    if not re.fullmatch(r"[0-9][0-9 \u00a0\u202f]*", text):
        raise serializers.ValidationError({field: "Un nombre entier, sans virgule ni signe."})
    number = int(re.sub(r"\D", "", text))
    if number > maximum:
        raise serializers.ValidationError({field: "Valeur trop élevée."})
    return number


class CouponSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display")
    trades = serializers.SerializerMethodField()
    zones = serializers.SerializerMethodField()
    starts_on = serializers.SerializerMethodField()
    ends_on = serializers.SerializerMethodField()
    uses = serializers.IntegerField(source="n_uses", default=0)
    discount_total = serializers.IntegerField(source="sum_discount", default=0)
    state = serializers.SerializerMethodField()

    class Meta:
        model = Coupon
        fields = [
            "id",
            "code",
            "description",
            "kind",
            "kind_label",
            "value",
            "max_discount",
            "min_amount",
            "starts_on",
            "ends_on",
            "max_uses",
            "max_uses_per_client",
            "first_order_only",
            "trades",
            "zones",
            "is_active",
            "uses",
            "discount_total",
            "state",
        ]

    def get_trades(self, c) -> list[dict]:
        return [{"slug": t.slug, "name": t.name} for t in c.trades.all()]

    def get_zones(self, c) -> list[dict]:
        return [{"slug": z.slug, "name": z.name} for z in c.zones.all()]

    def get_starts_on(self, c) -> str | None:
        return _local_date(c.starts_at)

    def get_ends_on(self, c) -> str | None:
        return _local_date(c.ends_at - timedelta(seconds=1)) if c.ends_at else None

    def get_state(self, c) -> str:
        """active | scheduled | expired | exhausted | off"""
        now = timezone.now()
        if not c.is_active:
            return "off"
        if c.starts_at and c.starts_at > now:
            return "scheduled"
        if c.ends_at and c.ends_at <= now:
            return "expired"
        if c.max_uses is not None and getattr(c, "n_uses", 0) >= c.max_uses:
            return "exhausted"
        return "active"


class CouponInputSerializer(PeriodFields):
    code = serializers.RegexField(r"^[A-Za-z0-9-]{3,20}$", max_length=20)
    description = serializers.CharField(
        max_length=160, required=False, allow_blank=True, default=""
    )
    kind = serializers.ChoiceField(choices=Coupon.Kind.choices)
    value = serializers.CharField()
    max_discount = serializers.CharField(required=False, allow_blank=True, default="")
    min_amount = serializers.CharField(required=False, allow_blank=True, default="")
    max_uses = serializers.CharField(required=False, allow_blank=True, default="")
    max_uses_per_client = serializers.IntegerField(min_value=1, max_value=50, default=1)
    first_order_only = serializers.BooleanField(default=False)
    trades = serializers.SlugRelatedField(
        slug_field="slug", queryset=Trade.objects.all(), many=True, required=False, default=list
    )
    zones = serializers.SlugRelatedField(
        slug_field="slug", queryset=Zone.objects.all(), many=True, required=False, default=list
    )
    is_active = serializers.BooleanField(default=True)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        attrs["code"] = attrs["code"].upper()
        value = _optional_int(attrs["value"], 10_000_000, "value")
        if not value:
            raise serializers.ValidationError({"value": "Indiquez la valeur de la remise."})
        if attrs["kind"] == Coupon.Kind.PERCENT and value > 100:
            raise serializers.ValidationError({"value": "Un pourcentage va de 1 à 100."})
        attrs["value"] = value
        attrs["max_discount"] = _optional_int(attrs["max_discount"], 10_000_000, "max_discount")
        attrs["min_amount"] = _optional_int(attrs["min_amount"], 10_000_000, "min_amount")
        attrs["max_uses"] = _optional_int(attrs["max_uses"], 1_000_000, "max_uses")
        if attrs["kind"] == Coupon.Kind.FIXED:
            attrs["max_discount"] = None
        return attrs


class CampaignSerializer(serializers.ModelSerializer):
    placement_label = serializers.CharField(source="get_placement_display")
    coupon_code = serializers.SerializerMethodField()
    starts_on = serializers.SerializerMethodField()
    ends_on = serializers.SerializerMethodField()
    is_live = serializers.SerializerMethodField()

    class Meta:
        model = Campaign
        fields = [
            "id",
            "title",
            "message",
            "cta_label",
            "cta_url",
            "coupon_code",
            "placement",
            "placement_label",
            "starts_on",
            "ends_on",
            "is_active",
            "is_live",
        ]

    def get_coupon_code(self, c) -> str:
        return c.coupon.code if c.coupon_id else ""

    def get_starts_on(self, c) -> str | None:
        return _local_date(c.starts_at)

    def get_ends_on(self, c) -> str | None:
        return _local_date(c.ends_at - timedelta(seconds=1)) if c.ends_at else None

    def get_is_live(self, c) -> bool:
        now = timezone.now()
        return (
            c.is_active
            and (c.starts_at is None or c.starts_at <= now)
            and (c.ends_at is None or c.ends_at > now)
        )


class CampaignInputSerializer(PeriodFields):
    title = serializers.CharField(max_length=80)
    message = serializers.CharField(max_length=200)
    cta_label = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    cta_url = serializers.RegexField(
        r"^(/(?!/)[\w\-/?=&.%]*)?$", max_length=200, required=False, allow_blank=True, default=""
    )
    coupon_code = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    placement = serializers.ChoiceField(choices=Campaign.Placement.choices)
    is_active = serializers.BooleanField(default=True)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        code = attrs.pop("coupon_code", "").strip().upper()
        attrs["coupon"] = None
        if code:
            attrs["coupon"] = Coupon.objects.filter(code=code).first()
            if attrs["coupon"] is None:
                raise serializers.ValidationError({"coupon_code": "Code promo inconnu."})
        if attrs["cta_label"] and not attrs["cta_url"]:
            raise serializers.ValidationError({"cta_url": "Indiquez la page du bouton."})
        return attrs


class TransactionSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display")
    trade = serializers.CharField(source="trade.name")
    zone = serializers.CharField(source="zone.name")
    client = serializers.SerializerMethodField()
    pro = serializers.SerializerMethodField()
    coupon = serializers.SerializerMethodField()
    client_pays = serializers.SerializerMethodField()
    net = serializers.SerializerMethodField()

    class Meta:
        model = ServiceRequest
        fields = [
            "id",
            "title",
            "status",
            "status_label",
            "trade",
            "zone",
            "client",
            "pro",
            "price",
            "discount",
            "coupon",
            "commission_rate",
            "commission",
            "client_pays",
            "net",
            "updated_at",
        ]

    def get_client(self, r) -> dict:
        return short(r.client)

    def get_pro(self, r) -> dict | None:
        return short(r.pro)

    def get_coupon(self, r) -> str:
        return r.coupon.code if r.coupon_id else ""

    def get_client_pays(self, r) -> int:
        return r.price - r.discount

    def get_net(self, r) -> int:
        return r.commission - r.discount


class SettlementSerializer(serializers.ModelSerializer):
    direction_label = serializers.CharField(source="get_direction_display")
    method_label = serializers.CharField(source="get_method_display")
    recorded_by = serializers.SerializerMethodField()

    class Meta:
        model = ProSettlement
        fields = [
            "id",
            "direction",
            "direction_label",
            "amount",
            "method",
            "method_label",
            "reference",
            "note",
            "recorded_by",
            "created_at",
        ]

    def get_recorded_by(self, s) -> dict | None:
        return short(s.recorded_by)


class SettlementInputSerializer(serializers.Serializer):
    direction = serializers.ChoiceField(choices=ProSettlement.Direction.choices)
    amount = serializers.CharField()
    method = serializers.ChoiceField(choices=ProSettlement.Method.choices)
    reference = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")

    def validate_amount(self, value) -> int:
        amount = _optional_int(value, 100_000_000, "amount")
        if not amount:
            raise serializers.ValidationError("Indiquez un montant en F CFA.")
        return amount


# --- Jef -----------------------------------------------------------------------------------------


class JefSessionSerializer(serializers.ModelSerializer):
    """Un échange avec Jef, tel que l'équipe le relit : texte, questions, réponses, fiche."""

    client = serializers.SerializerMethodField()
    trade = serializers.CharField(source="trade.name", default="")
    mode_label = serializers.CharField(source="get_mode_display")
    request = serializers.SerializerMethodField()

    class Meta:
        model = JefSession
        fields = [
            "id",
            "client",
            "trade",
            "mode",
            "mode_label",
            "text",
            "questions",
            "answers",
            "brief",
            "request",
            "created_at",
        ]

    def get_client(self, obj) -> dict | None:
        return short(obj.client)

    def get_request(self, obj) -> dict | None:
        req = obj.request
        return None if req is None else {"id": req.pk, "title": req.title, "status": req.status}
