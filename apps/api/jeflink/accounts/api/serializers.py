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
    """``authenticated`` : session ouverte. ``mfa_required`` / ``mfa_enrollment_required`` (Ops
    sur la console) : seulement ``mfa_token``, à présenter aux endpoints ``mfa/totp/*``."""

    status = serializers.ChoiceField(
        choices=["authenticated", "mfa_required", "mfa_enrollment_required"]
    )
    mfa_token = serializers.CharField(required=False)
    user = AuthUserSerializer(required=False)
    is_new_user = serializers.BooleanField(required=False)
    restricted = serializers.BooleanField(required=False)
    # Session restreinte (compte dormant) : type d'écran à afficher, sans rien de l'ancien
    # titulaire du numéro (I2).
    restriction_kind = serializers.ChoiceField(
        choices=["client", "pro"], allow_null=True, required=False
    )
    other_sessions = OtherSessionSerializer(many=True, required=False)
    pending_invitations = InvitationSerializer(many=True, required=False)
    tokens = TokenPairSerializer(required=False)

    def to_representation(self, instance: dict) -> dict:
        data = super().to_representation(instance)
        if data["status"] != "authenticated":
            # Aucune donnée du compte avant le second facteur.
            return {"status": data["status"], "mfa_token": data["mfa_token"]}
        return data


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


# --- Second facteur Ops (TOTP) ---------------------------------------------------------------


class MfaTokenSerializer(serializers.Serializer):
    mfa_token = serializers.CharField(max_length=128)


class TotpSetupRequestSerializer(MfaTokenSerializer):
    enrollment_token = serializers.CharField(max_length=128)


class TotpSetupResponseSerializer(serializers.Serializer):
    secret = serializers.CharField()
    otpauth_uri = serializers.CharField()


class TotpCodeRequestSerializer(MfaTokenSerializer):
    code = serializers.RegexField(r"^[0-9]{6}$")


class StepUpRequestSerializer(serializers.Serializer):
    code = serializers.RegexField(r"^[0-9]{6}$")


class AccessTokenSerializer(serializers.Serializer):
    access = serializers.CharField()
    access_expires_at = serializers.DateTimeField()


# --- Suppression du compte -------------------------------------------------------------------


class DeletionConfirmSerializer(serializers.Serializer):
    challenge_id = serializers.UUIDField()
    challenge_secret = serializers.CharField(max_length=64)
    code = serializers.RegexField(r"^[0-9]{6}$")


# --- Ops : comptes -----------------------------------------------------------------------------


class OpsSearchSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=32)


class OpsAccountSummarySerializer(serializers.Serializer):
    public_id = serializers.UUIDField()
    phone_masked = serializers.CharField()
    display_name = serializers.CharField()
    profile_status = serializers.CharField()
    is_active = serializers.BooleanField()
    roles = serializers.ListField(child=serializers.CharField())


class OpsSearchResultSerializer(serializers.Serializer):
    results = OpsAccountSummarySerializer(many=True)


class OpsSessionSerializer(serializers.Serializer):
    public_id = serializers.UUIDField()
    app = serializers.CharField()
    platform = serializers.CharField()
    device_label = serializers.CharField()
    restricted = serializers.BooleanField()
    last_seen_at = serializers.DateTimeField()
    created_at = serializers.DateTimeField()


class OpsAccountDetailSerializer(OpsAccountSummarySerializer):
    preferred_language = serializers.CharField()
    deactivation_reason = serializers.CharField()
    deleted = serializers.BooleanField()
    dormant_restricted = serializers.BooleanField()
    otp_blocked_until = serializers.DateTimeField(allow_null=True)
    sessions = OpsSessionSerializer(many=True)
    created_at = serializers.DateTimeField()
    phone_verified_at = serializers.DateTimeField(allow_null=True)
    phone_changed_at = serializers.DateTimeField(allow_null=True)


def ops_action_serializer(action: str) -> type[serializers.Serializer]:
    """Motif énuméré propre à l'action, note facultative (filtrée par le service)."""
    from jeflink.accounts.ops import REASONS

    name = "".join(part.capitalize() for part in action.split("_"))
    return type(
        f"Ops{name}RequestSerializer",
        (serializers.Serializer,),
        {
            "reason_code": serializers.ChoiceField(choices=REASONS[action]),
            "note": serializers.CharField(
                max_length=400, required=False, default="", allow_blank=True
            ),
        },
    )


class RevealedPhoneSerializer(serializers.Serializer):
    phone = serializers.CharField()


# --- Changement de numéro (S2) -----------------------------------------------------------------


class PhoneChangeCreateSerializer(serializers.Serializer):
    new_phone = serializers.CharField(max_length=32)
    reason_code = serializers.ChoiceField(
        choices=["sim_lost_new_number", "number_changed", "operator_change"]
    )
    note = serializers.CharField(max_length=400, required=False, default="", allow_blank=True)


class PhoneChangeRejectSerializer(serializers.Serializer):
    reason_code = serializers.ChoiceField(
        choices=["proof_insufficient", "suspected_fraud", "request_error"]
    )
    note = serializers.CharField(max_length=400, required=False, default="", allow_blank=True)


class PhoneChangeRequestSerializer(serializers.Serializer):
    public_id = serializers.UUIDField()
    account = serializers.UUIDField(source="user.public_id")
    current_phone_masked = serializers.SerializerMethodField()
    new_phone_masked = serializers.SerializerMethodField()
    requested_by = serializers.UUIDField(source="requested_by.public_id")
    requires_approval = serializers.BooleanField()
    reason_code = serializers.CharField()
    status = serializers.CharField()
    codes_sent = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    expires_at = serializers.DateTimeField()

    def get_current_phone_masked(self, obj) -> str:
        from jeflink.common.pii import mask_phone

        return mask_phone(obj.user.phone) if obj.user.phone else ""

    def get_new_phone_masked(self, obj) -> str:
        from jeflink.common.pii import mask_phone

        return mask_phone(obj.new_phone) if obj.new_phone else ""


class PhoneChangeConfirmSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=32)
    code = serializers.RegexField(r"^[0-9]{6}$")
    terms_version = serializers.CharField(max_length=16)
    device = DeviceSerializer()
    app = serializers.ChoiceField(choices=["client", "pro"], required=False)
