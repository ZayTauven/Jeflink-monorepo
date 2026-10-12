from django.contrib.auth import authenticate, password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers

from jeflink.catalog.models import Trade, Zone

from .models import ContactMessage, ProProfile, User, normalize_phone


class ProProfileSerializer(serializers.ModelSerializer):
    trades = serializers.SlugRelatedField(slug_field="slug", many=True, read_only=True)
    zones = serializers.SlugRelatedField(slug_field="slug", many=True, read_only=True)

    class Meta:
        model = ProProfile
        fields = [
            "headline",
            "bio",
            "trades",
            "zones",
            "years_experience",
            "is_verified",
            "verification_note",
            "photo",
        ]


class MeSerializer(serializers.ModelSerializer):
    pro_profile = ProProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "phone",
            "role",
            "is_staff",
            "pro_profile",
        ]


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
        slug_field="slug", queryset=Zone.objects.filter(is_active=True), many=True, required=False
    )
    headline = serializers.CharField(max_length=120, required=False, allow_blank=True)

    def validate_email(self, value):
        value = value.lower()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Un compte existe déjà avec cet email.")
        return value

    def validate_phone(self, value):
        try:
            return normalize_phone(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc

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
