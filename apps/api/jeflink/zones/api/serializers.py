from rest_framework import serializers

from jeflink.common.api.reference import LocalizedTextField


class ZoneSerializer(serializers.Serializer):
    """Zone dans une liste : ni position, ni géométrie (spec 002)."""

    slug = serializers.CharField()
    name = serializers.CharField()
    city = serializers.CharField(source="city.slug")
    aliases = serializers.ListField(child=serializers.CharField())


class NearbyZoneSerializer(serializers.Serializer):
    """Zone voisine : un lien, rien de plus (ni distance, ni position)."""

    slug = serializers.CharField()
    name = serializers.CharField()


class ZoneDetailSerializer(ZoneSerializer):
    """Détail pour la page métier et quartier (spec 006) : textes saisis par l'Ops, voisins."""

    # Forme grammaticale (« aux Almadies ») et intro du quartier ; ``null`` tant que le français
    # est vide (repli côté web : « à {nom} »).
    locative = LocalizedTextField("locative", optional=True)
    intro = LocalizedTextField("seo_intro", optional=True)
    indexable = serializers.BooleanField(
        help_text="Vrai quand le quartier a son texte d'intro : sinon la page est noindex."
    )
    nearby = NearbyZoneSerializer(many=True, source="nearby_zones")


class CoveragePairSerializer(serializers.Serializer):
    """Une paire métier et zone ouverte : une page du site (et une ligne du sitemap)."""

    trade = serializers.CharField(help_text="Slug du métier.")
    zone = serializers.CharField(help_text="Slug de la zone.")
    indexable = serializers.BooleanField()
    updated_at = serializers.DateTimeField()
