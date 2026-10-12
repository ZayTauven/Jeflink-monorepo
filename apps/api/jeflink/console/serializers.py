"""Sérialiseurs de la console : l'équipe voit noms complets, emails et téléphones (support)."""

from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from jeflink.accounts.models import ContactMessage, ProProfile, User, normalize_phone
from jeflink.catalog.models import Trade, Zone
from jeflink.jobs import services as jobs_services
from jeflink.jobs.models import Dispute, Quote, RequestEvent, Review, ServiceRequest

from .models import AuditLog, PlatformSettings


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
        digits = "".join(ch for ch in value if ch.isdigit())
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
