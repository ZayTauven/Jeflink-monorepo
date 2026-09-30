from rest_framework import serializers

from jeflink.accounts.models import DeviceSession, User


class RefreshRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField(max_length=128, trim_whitespace=True)


class TokenPairSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
    access_expires_at = serializers.DateTimeField()


class DeviceSessionSerializer(serializers.ModelSerializer):
    is_current = serializers.SerializerMethodField()

    class Meta:
        model = DeviceSession
        fields = [
            "public_id",
            "app",
            "platform",
            "device_label",
            "last_seen_at",
            "created_at",
            "is_current",
        ]
        read_only_fields = fields

    def get_is_current(self, obj: DeviceSession) -> bool:
        return str(obj.public_id) == str(self.context.get("current_sid"))


# --- OTP -------------------------------------------------------------------------------------


class RegionSerializer(serializers.Serializer):
    region = serializers.CharField()
    dial_code = serializers.CharField()
    label = serializers.CharField()


class AuthConfigSerializer(serializers.Serializer):
    regions = RegionSerializer(many=True)
    code_length = serializers.IntegerField()
    client_challenge_required = serializers.BooleanField()
    terms_version = serializers.CharField()


class OtpRequestSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=32)
    # Mobile seulement : « web » et « console » sont imposés par le BFF de confiance (S10).
    app = serializers.ChoiceField(choices=["client", "pro"], required=False)
    client_challenge_token = serializers.CharField(max_length=4096, required=False, default="")


class OtpChallengeResponseSerializer(serializers.Serializer):
    challenge_id = serializers.UUIDField()
    challenge_secret = serializers.CharField(required=False)
    phone_display = serializers.CharField()
    code_length = serializers.IntegerField()
    expires_at = serializers.DateTimeField()
    resend_available_at = serializers.DateTimeField()
    deliveries_remaining = serializers.IntegerField()


class OtpResendSerializer(serializers.Serializer):
    challenge_id = serializers.UUIDField()
    challenge_secret = serializers.CharField(max_length=64)


class DeviceSerializer(serializers.Serializer):
    platform = serializers.ChoiceField(choices=["android", "ios", "web"])
    label = serializers.CharField(max_length=120, required=False, default="", allow_blank=True)
    install_id = serializers.CharField(max_length=64, required=False, default="", allow_blank=True)


class OtpVerifySerializer(serializers.Serializer):
    challenge_id = serializers.UUIDField()
    challenge_secret = serializers.CharField(max_length=64)
    # Chiffres ASCII seulement : \d accepterait des chiffres d'autres écritures (M8).
    code = serializers.RegexField(r"^[0-9]{6}$")
    terms_version = serializers.CharField(max_length=16)
    device = DeviceSerializer()
    app = serializers.ChoiceField(choices=["client", "pro"], required=False)


class AuthUserSerializer(serializers.Serializer):
    public_id = serializers.UUIDField()
    phone_display = serializers.CharField()
    display_name = serializers.CharField()
    profile_status = serializers.CharField()
    preferred_language = serializers.CharField()
    roles = serializers.ListField(child=serializers.CharField())


class InvitationSerializer(serializers.Serializer):
    public_id = serializers.UUIDField()
    role = serializers.ChoiceField(choices=["owner", "technician"])
    # Nom affiché du pro qui invite ; celui de son équipe viendra de providers (context_ref).
    invited_by_name = serializers.CharField(source="invited_by.display_name")
    # Nom proposé par le pro : s'il existe, l'écran « Comment doit-on vous appeler ? » est sauté.
    display_name_hint = serializers.CharField()
    context_ref = serializers.UUIDField()
    expires_at = serializers.DateTimeField()


class AcceptInvitationSerializer(serializers.Serializer):
    # Nom saisi ou confirmé par l'invité sur l'écran d'acceptation (profil invité seulement).
    display_name = serializers.CharField(
        max_length=256, required=False, default="", allow_blank=True, trim_whitespace=False
    )


class OtherSessionSerializer(serializers.Serializer):
    public_id = serializers.UUIDField()
    app = serializers.CharField()
    device_label = serializers.CharField()
    last_seen_at = serializers.DateTimeField()


class OtpVerifyResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    user = AuthUserSerializer()
    is_new_user = serializers.BooleanField()
    restricted = serializers.BooleanField()
    # Session restreinte (compte dormant) : type d'écran à afficher, sans rien de l'ancien
    # titulaire du numéro (I2).
    restriction_kind = serializers.ChoiceField(choices=["client", "pro"], allow_null=True)
    other_sessions = OtherSessionSerializer(many=True)
    pending_invitations = InvitationSerializer(many=True)
    tokens = TokenPairSerializer()


# --- Profil ----------------------------------------------------------------------------------


class MeSerializer(serializers.Serializer):
    public_id = serializers.UUIDField()
    phone = serializers.CharField()
    phone_display = serializers.CharField()
    display_name = serializers.CharField()
    email = serializers.CharField()
    preferred_language = serializers.ChoiceField(choices=User.Language.choices)
    profile_status = serializers.ChoiceField(choices=User.ProfileStatus.choices)
    roles = serializers.ListField(child=serializers.CharField())
    # Nul pour une session restreinte : rien de l'ancien titulaire (I2).
    created_at = serializers.DateTimeField(allow_null=True)
    restricted = serializers.BooleanField()
    restriction_kind = serializers.ChoiceField(choices=["client", "pro"], allow_null=True)


class MeUpdateSerializer(serializers.Serializer):
    # Borne de taille seulement : les règles du nom (2 à 80 caractères, termes réservés…)
    # sont celles du service, avec leurs codes d'erreur propres.
    display_name = serializers.CharField(
        max_length=256, required=False, allow_blank=True, trim_whitespace=False
    )
    email = serializers.EmailField(max_length=254, required=False, allow_blank=True)
    preferred_language = serializers.ChoiceField(choices=User.Language.choices, required=False)
