"""Lectures des avis (spec 004)."""

from collections.abc import Iterable
from datetime import datetime

from django.conf import settings
from django.db.models import Avg, Count, QuerySet
from django.utils import timezone

from jeflink.bookings.models import Booking

from .models import Review


def counted_reviews() -> QuerySet[Review]:
    """Avis qui comptent dans une moyenne : publiés, non masqués, ni d'un compte de revue des
    stores, ni d'un pro de démonstration."""
    return Review.objects.filter(
        published_at__isnull=False,
        hidden_at__isnull=True,
        provider__is_demo=False,
        booking__client__is_review_account=False,
    )


def rating_for_providers(provider_ids: Iterable[int]) -> dict[int, dict | None]:
    """``{provider_id: {"average": 4.3, "count": 12}}`` : moyenne à 1 décimale des avis publiés
    et non masqués. ``None`` sous ``REVIEWS_MIN_DISPLAY`` avis (« Nouveau sur Jeflink »). Une
    seule requête pour tous les pros."""
    ids = set(provider_ids)
    rows = (
        counted_reviews()
        .filter(provider_id__in=ids)
        .values("provider_id")
        .annotate(average=Avg("rating"), count=Count("pk"))
    )
    found = {
        row["provider_id"]: (
            {"average": round(float(row["average"]), 1), "count": row["count"]}
            if row["count"] >= settings.REVIEWS_MIN_DISPLAY
            else None
        )
        for row in rows
    }
    return {pid: found.get(pid) for pid in ids}


def review_deadline(booking: Booking) -> datetime | None:
    """Fin du droit d'avis : 14 jours après « terminé », ou 7 jours après une décision de litige
    en faveur du client si c'est plus tard. ``None`` si la mission n'est pas terminée."""
    if booking.completed_at is None:
        return None
    deadline = booking.completed_at + settings.REVIEW_WINDOW
    dispute = getattr(booking, "dispute", None)
    if dispute is not None and dispute.decision == "for_client" and dispute.resolved_at:
        deadline = max(deadline, dispute.resolved_at + settings.REVIEW_WINDOW_AFTER_DISPUTE)
    return deadline


def can_review(booking: Booking, *, now: datetime | None = None) -> bool:
    deadline = review_deadline(booking)
    if deadline is None or booking.status not in {"completed", "disputed", "closed"}:
        return False
    return (now or timezone.now()) <= deadline


def published_review_for_provider(booking: Booking) -> Review | None:
    """L'avis tel que le pro le voit : publié et non masqué seulement."""
    review = getattr(booking, "review", None)
    if review is None or review.published_at is None or review.hidden_at is not None:
        return None
    return review
