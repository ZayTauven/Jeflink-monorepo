"""Lectures des pros (spec 003)."""

from django.db.models import Count, Q, QuerySet

from jeflink.accounts.models import User

from .models import Provider


def provider_for_owner(user: User) -> Provider | None:
    """Fiche du gérant, quel que soit son statut (un pro suspendu lit encore ses réservations)."""
    return Provider.objects.filter(owner=user).prefetch_related("trades", "zones").first()


def providers_for_admin() -> QuerySet[Provider]:
    # Fins de mission par pro : la part « sans code » est visible de l'Ops (spec 004).
    done = Q(bookings__completion_method__in=("code", "no_code"))
    return (
        Provider.objects.select_related("owner")
        .prefetch_related("trades", "zones")
        .annotate(
            completions=Count("bookings", filter=done),
            no_code_completions=Count("bookings", filter=Q(bookings__completion_method="no_code")),
        )
    )
