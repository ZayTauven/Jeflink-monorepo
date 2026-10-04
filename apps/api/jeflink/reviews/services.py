"""Écritures des avis (spec 004). Le commentaire n'est jamais écrit dans un log ni un audit."""

from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.utils import timezone

from jeflink.accounts.models import User
from jeflink.bookings.models import Booking
from jeflink.common.errors import DomainError
from jeflink.trust.models import AuditEvent
from jeflink.trust.services import audit

from .models import HIDE_REASONS, NEGATIVE_TAGS, POSITIVE_TAGS, Review
from .selectors import can_review


@dataclass(frozen=True)
class SubmittedReview:
    review: Review
    created: bool


def clean_review(*, rating: int, tags: list[str], comment: str) -> tuple[int, list[str], str]:
    """Une note de 1 à 5 suffit. Puces : les quatre positives, et sous 3 étoiles les quatre
    négatives ; sans doublon. Commentaire facultatif (500 caractères). ``422 review_invalid``."""
    from django.conf import settings

    if isinstance(rating, bool) or not isinstance(rating, int) or not 1 <= rating <= 5:
        raise DomainError("review_invalid", status=422)
    allowed = set(POSITIVE_TAGS) | (set(NEGATIVE_TAGS) if rating < 3 else set())
    clean_tags = list(dict.fromkeys(tags or []))
    if any(tag not in allowed for tag in clean_tags):
        raise DomainError("review_invalid", status=422)
    text = " ".join((comment or "").split())
    if len(text) > settings.REVIEW_COMMENT_MAX:
        raise DomainError("review_invalid", status=422)
    return rating, clean_tags, text


def submit_review(
    *, booking: Booking, actor: User, rating: int, tags: list[str], comment: str
) -> SubmittedReview:
    """Le client note une réservation terminée (créé ou modifié, un seul avis par réservation).

    Seul le client de la réservation ; de ``completed`` (litige compris) jusqu'à 14 jours après
    (7 jours après une décision en sa faveur) : ``409 review_not_allowed`` (mission non terminée),
    ``409 review_window_closed``, ``422 review_invalid``. Publié tout de suite si la réservation
    est déjà close, sinon à la clôture. Jamais exigé : la clôture n'en dépend pas.
    """
    rating, tags, comment = clean_review(rating=rating, tags=tags, comment=comment)
    try:
        with transaction.atomic():
            return _upsert(booking, actor, rating, tags, comment)
    except IntegrityError:
        # Deux premiers envois simultanés : le second met à jour l'avis du premier.
        with transaction.atomic():
            return _upsert(booking, actor, rating, tags, comment)


def _upsert(booking: Booking, actor: User, rating: int, tags: list[str], comment: str):
    booking = (
        Booking.objects.select_for_update(of=("self",)).select_related("dispute").get(pk=booking.pk)
    )
    if booking.client_id != actor.id:
        raise DomainError("not_found", status=404)
    if booking.completed_at is None or booking.status not in {"completed", "disputed", "closed"}:
        raise DomainError("review_not_allowed", status=409)
    if not can_review(booking):
        raise DomainError("review_window_closed", status=409)
    now = timezone.now()
    review = Review.objects.select_for_update().filter(booking=booking).first()
    created = review is None
    if created:
        review = Review(booking=booking, provider_id=booking.provider_id, author=actor)
        if booking.status == "closed":
            review.published_at = now
    else:
        review.edited_at = now
    review.rating, review.tags, review.comment = rating, tags, comment
    review.save()
    audit(
        action="reviews.review.submitted",
        actor=actor,
        target=review,
        metadata={"rating": rating, "edited": not created},
    )
    return SubmittedReview(review, created)


def publish_on_close(booking: Booking, reason: str) -> None:
    """Gestionnaire de clôture : publie l'avis déjà déposé (idempotent)."""
    Review.objects.filter(booking=booking, published_at__isnull=True).update(
        published_at=timezone.now()
    )


@transaction.atomic
def hide_review(*, review: Review, reason: str, operator: User) -> Review:
    """L'Ops masque un avis (jamais supprimé) : il sort de la moyenne et de la vue du pro."""
    if reason not in HIDE_REASONS:
        raise DomainError("reason_invalid", status=422)
    review = Review.objects.select_for_update().get(pk=review.pk)
    if review.hidden_at is None:
        review.hidden_at = timezone.now()
        review.hidden_reason = reason
        review.hidden_by = operator
        review.save(update_fields=["hidden_at", "hidden_reason", "hidden_by", "updated_at"])
        audit(
            action="reviews.review.hidden",
            actor=operator,
            actor_kind=AuditEvent.ActorKind.OPS,
            target=review,
            metadata={"reason": reason},
        )
    return review


@transaction.atomic
def restore_review(*, review: Review, operator: User) -> Review:
    review = Review.objects.select_for_update().get(pk=review.pk)
    if review.hidden_at is not None:
        review.hidden_at = None
        review.hidden_reason = ""
        review.hidden_by = None
        review.save(update_fields=["hidden_at", "hidden_reason", "hidden_by", "updated_at"])
        audit(
            action="reviews.review.restored",
            actor=operator,
            actor_kind=AuditEvent.ActorKind.OPS,
            target=review,
        )
    return review


def anonymize_reviews(user: User) -> None:
    """Anonymiseur : le commentaire est vidé et l'auteur détaché, la note est gardée."""
    Review.objects.filter(author=user).update(comment="", author=None, updated_at=timezone.now())
