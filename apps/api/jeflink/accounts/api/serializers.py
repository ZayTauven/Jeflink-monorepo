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
