from django.contrib.auth import authenticate, password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers

from jeflink.catalog.models import Trade, served_zones
from jeflink.jobs.models import Quote

from .models import ContactMessage, ProDocument, ProProfile, SavedAddress, User, normalize_phone


def clean_phone(value: str) -> str:
    try:
        return normalize_phone(value)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(exc.messages) from exc


class AddressSerializer(serializers.ModelSerializer):
    zone = serializers.SlugRelatedField(slug_field="slug", queryset=served_zones())
    zone_name = serializers.CharField(source="zone.name", read_only=True)

    class Meta:
        model = SavedAddress
        fields = ["id", "label", "zone", "zone_name", "landmark"]


class DocumentSerializer(serializers.ModelSerializer):
    """Un justificatif, sans son chemin : le fichier se lit par /api/auth/documents/<id>/file/."""

    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = ProDocument
        fields = [
            "id",
            "kind",
            "kind_label",
            "status",
            "status_label",
            "note",
            "content_type",
            "created_at",
            "reviewed_at",
        ]


class ProProfileSerializer(serializers.ModelSerializer):
    trades = serializers.SlugRelatedField(slug_field="slug", many=True, read_only=True)
    pending_trades = serializers.SlugRelatedField(slug_field="slug", many=True, read_only=True)
    zones = serializers.SlugRelatedField(slug_field="slug", many=True, read_only=True)
    documents = DocumentSerializer(many=True, read_only=True)

    class Meta:
        model = ProProfile
        fields = [
            "headline",
            "bio",
            "trades",
            "pending_trades",
            "trade_note",
            "zones",
            "years_experience",
            "is_verified",
            "verification_note",
            "photo",
            "documents",
        ]


class MeSerializer(serializers.ModelSerializer):
    pro_profile = ProProfileSerializer(read_only=True)
    console_role = serializers.CharField(read_only=True)
    console_sections = serializers.SerializerMethodField()
    addresses = AddressSerializer(many=True, read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "phone",
            "photo",
            "contact_pref",
            "contact_hours",
            "role",
            "is_staff",
            "console_role",
            "console_sections",
            "addresses",
            "pro_profile",
        ]

    def get_console_sections(self, user) -> list[str]:
        from jeflink.console.permissions import sections_for

        return sections_for(user)


class ProfileSerializer(serializers.Serializer):
    """Mon profil (formulaire complet) : identité, téléphone, comment me joindre ; pour un pro,
    aussi accroche, présentation, expérience et quartiers. Les métiers ont leur propre parcours."""

    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    phone = serializers.CharField(required=False, allow_blank=True, default="")
    contact_pref = serializers.ChoiceField(User.ContactPref.choices, required=False, default="")
    contact_hours = serializers.ChoiceField(User.ContactHours.choices, required=False, default="")
    # Pro uniquement (ignorés pour un client)
    headline = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    bio = serializers.CharField(max_length=1500, required=False, allow_blank=True, default="")
    years_experience = serializers.IntegerField(
        min_value=0, max_value=60, required=False, default=0
    )
    zones = serializers.SlugRelatedField(
        slug_field="slug", queryset=served_zones(), many=True, required=False
    )
    # Métiers voulus : retirés tout de suite, ajoutés « demandés » (validés par l'équipe).
    trades = serializers.SlugRelatedField(
        slug_field="slug",
        queryset=Trade.objects.filter(is_active=True),
        many=True,
        required=False,
    )

    def validate_phone(self, value):
        return clean_phone(value)

    def validate_trades(self, value):
        if not value:
            raise serializers.ValidationError("Gardez au moins un métier.")
        profile = getattr(self.instance, "pro_profile", None)
        current = set(profile.trades.all()) if profile else set()
        if current and not set(value) & current:
            # Sinon un pro vérifié se retrouverait sans aucun métier validé.
            raise serializers.ValidationError("Gardez au moins un de vos métiers déjà validés.")
        return value

    def validate(self, attrs):
        """Pro vérifié : nom et téléphone ont été contrôlés avec sa pièce d'identité ; ils ne
        changent qu'avec le support (sinon le badge « Vérifié » couvrirait quelqu'un d'autre)."""
        user = self.instance
        profile = getattr(user, "pro_profile", None)
        checked = (user.first_name, user.last_name, user.phone)
        wanted = (attrs["first_name"], attrs["last_name"], attrs["phone"])
        if profile and profile.is_verified and wanted != checked:
            raise serializers.ValidationError(
                "Nom et téléphone vérifiés avec votre pièce d'identité : écrivez au "
                "support pour les changer."
            )
        return attrs

    @transaction.atomic
    def update(self, user, data):
        for key in ("first_name", "last_name", "phone", "contact_pref", "contact_hours"):
            setattr(user, key, data[key])
        user.save()
        profile = getattr(user, "pro_profile", None)
        if profile is not None:
            profile.headline = data["headline"]
            profile.bio = data["bio"]
            profile.years_experience = data["years_experience"]
            profile.save(update_fields=["headline", "bio", "years_experience"])
            if "zones" in data:
                profile.zones.set(data["zones"])
            if "trades" in data:
                wanted = set(data["trades"])
                current = set(profile.trades.all())
                removed = current - wanted
                profile.trades.remove(*removed)
                profile.pending_trades.set(wanted - current)
                # Ses devis en attente sur un métier retiré ne peuvent plus être choisis.
                Quote.objects.filter(
                    pro=user, status=Quote.Status.PENDING, request__trade__in=removed
                ).update(status=Quote.Status.DECLINED)
        return user


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)
    role = serializers.ChoiceField(choices=User.Role.choices, default=User.Role.CLIENT)
    # Pro uniquement
    trades = serializers.SlugRelatedField(
        slug_field="slug", queryset=Trade.objects.filter(is_active=True), many=True, required=False
    )
    zones = serializers.SlugRelatedField(
        slug_field="slug", queryset=served_zones(), many=True, required=False
    )
    headline = serializers.CharField(max_length=120, required=False, allow_blank=True)

    def validate_email(self, value):
        value = value.lower()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Un compte existe déjà avec cet email.")
        return value

    def validate_phone(self, value):
        return clean_phone(value)

    def validate(self, attrs):
        if attrs.get("role") == User.Role.PRO and not attrs.get("trades"):
            raise serializers.ValidationError({"trades": "Choisissez au moins un métier."})
        candidate = User(email=attrs["email"], first_name=attrs["first_name"])
        try:
            password_validation.validate_password(attrs["password"], candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": exc.messages}) from exc
        return attrs

    @transaction.atomic
    def create(self, data):
        trades = data.pop("trades", [])
        zones = data.pop("zones", [])
        headline = data.pop("headline", "")
        user = User.objects.create_user(**data)
        if user.is_pro:
            profile = ProProfile.objects.create(user=user, headline=headline)
            profile.trades.set(trades)
            profile.zones.set(zones)
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = authenticate(
            self.context["request"], email=attrs["email"].lower(), password=attrs["password"]
        )
        if user is None:
            raise serializers.ValidationError("Email ou mot de passe incorrect.")
        attrs["user"] = user
        return attrs


class ContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactMessage
        fields = ["name", "email", "message"]
