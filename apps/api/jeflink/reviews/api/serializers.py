"""Sérialiseurs des avis (spec 004). Aucune logique métier."""

from typing import Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from jeflink.common.pii import mask_numbers
from jeflink.reviews.models import Review


class RatingSerializer(serializers.Serializer):
    """Note d'un pro : moyenne à 1 décimale et nombre d'avis publiés. Le champ vaut ``null`` sous
    3 avis : le front affiche « Nouveau sur Jeflink »."""

    average = serializers.FloatField()
    count = serializers.IntegerField()


class ClientReviewSerializer(serializers.ModelSerializer):
    """L'avis vu de son auteur : toujours le sien, publié ou non."""

    published = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = [
            "rating",
            "tags",
            "comment",
            "published",
            "published_at",
            "edited_at",
            "created_at",
        ]
        read_only_fields = fields

    def get_published(self, review: Review) -> bool:
        return review.published_at is not None


class ProReviewSerializer(serializers.ModelSerializer):
    """L'avis vu du pro, une fois publié : les numéros du commentaire sont masqués."""

    comment = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = ["rating", "tags", "comment", "published_at"]
        read_only_fields = fields

    @extend_schema_field(serializers.CharField())
    def get_comment(self, review: Review) -> Any:
        return mask_numbers(review.comment)[0]


class ReviewWriteSerializer(serializers.Serializer):
    """Une note suffit. Valeurs vérifiées par le service (``422 review_invalid``)."""

    rating = serializers.IntegerField()
    tags = serializers.ListField(
        child=serializers.CharField(max_length=16), required=False, default=list
    )
    comment = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")
