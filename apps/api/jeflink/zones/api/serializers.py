from rest_framework import serializers


class ZoneSerializer(serializers.Serializer):
    """Zone dans une liste : ni position, ni géométrie (spec 002)."""

    slug = serializers.CharField()
    name = serializers.CharField()
    city = serializers.CharField(source="city.slug")
    aliases = serializers.ListField(child=serializers.CharField())
