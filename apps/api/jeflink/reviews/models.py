"""Avis (spec 004) : un par réservation terminée, par son client. Une note suffit ; le
commentaire est facultatif et ses numéros sont masqués à l'affichage. Publié à la clôture de la
réservation (le pro ne voit pas l'avis tant qu'il peut encore faire pression), masqué (jamais
supprimé) par l'Ops. Le commentaire n'est jamais écrit dans un log ni un audit.
"""

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import Q

from jeflink.common.models import BaseModel

POSITIVE_TAGS = ("on_time", "quality", "clean", "price_kept")
NEGATIVE_TAGS = ("late", "redo_needed", "messy", "price_changed")  # sous 3 étoiles seulement
HIDE_REASONS = ("abusive", "personal_data", "off_topic", "fake", "other")


class Review(BaseModel):
    booking = models.OneToOneField(
        "bookings.Booking", on_delete=models.PROTECT, related_name="review"
    )
    provider = models.ForeignKey(
        "providers.Provider", on_delete=models.PROTECT, related_name="reviews"
    )
    # Détaché à la suppression du compte du client (la note reste, le commentaire part).
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    rating = models.PositiveSmallIntegerField()
    tags = ArrayField(models.CharField(max_length=16), default=list, blank=True)
    comment = models.CharField(max_length=settings.REVIEW_COMMENT_MAX, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    hidden_at = models.DateTimeField(null=True, blank=True)
    hidden_reason = models.CharField(max_length=16, blank=True)
    hidden_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        verbose_name = "avis"
        verbose_name_plural = "avis"
        ordering = ("-created_at",)
        permissions = [("moderate_review", "Modération avis : masquer ou réafficher un avis")]
        indexes = [models.Index(fields=("provider", "published_at"))]
        constraints = [
            models.CheckConstraint(
                condition=Q(rating__gte=1) & Q(rating__lte=5), name="review_rating_1_to_5"
            ),
            models.CheckConstraint(
                condition=Q(hidden_at__isnull=True) | ~Q(hidden_reason=""),
                name="review_hidden_has_reason",
            ),
        ]

    def __str__(self) -> str:
        return f"avis {self.rating}/5"
