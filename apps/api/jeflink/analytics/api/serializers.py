from rest_framework import serializers


class PublicRatingSerializer(serializers.Serializer):
    average = serializers.FloatField(help_text="Moyenne sur 5, une décimale.")
    count = serializers.IntegerField()

    class Meta:
        ref_name = "PublicRating"


class QuietHoursSerializer(serializers.Serializer):
    start = serializers.IntegerField(help_text="Heure de Dakar (0-23) où le délai s'arrête.")
    end = serializers.IntegerField(help_text="Heure de Dakar (0-23) où il reprend.")


class PublicRulesSerializer(serializers.Serializer):
    """Règles réelles lues dans les réglages (specs 003 et 004) : le site ne les recopie pas."""

    max_quotes_per_request = serializers.IntegerField()
    dispute_window_hours = serializers.FloatField()
    pro_confirm_hours = serializers.FloatField()
    pro_confirm_hours_urgent = serializers.FloatField()
    quiet_hours = QuietHoursSerializer()


class PublicStatsSerializer(serializers.Serializer):
    """Chiffres publics à seuils : ``null`` sous le seuil, arrondis ; aucun nom ni identifiant."""

    missions_completed = serializers.IntegerField(
        allow_null=True, help_text="Arrondi à la dizaine inférieure ; null sous le seuil."
    )
    rating = PublicRatingSerializer(allow_null=True)
    verified_pros = serializers.IntegerField(
        allow_null=True,
        help_text="Exact de 3 à 9, dizaine inférieure au-delà ; null sous le seuil.",
    )
    rules = PublicRulesSerializer()
