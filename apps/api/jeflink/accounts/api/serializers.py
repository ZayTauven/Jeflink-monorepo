from rest_framework import serializers

from jeflink.accounts.models import DeviceSession


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
    code = serializers.RegexField(r"^\d{6}$")
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
    other_sessions = OtherSessionSerializer(many=True)
    pending_invitations = serializers.ListField(child=serializers.DictField())
    tokens = TokenPairSerializer()
