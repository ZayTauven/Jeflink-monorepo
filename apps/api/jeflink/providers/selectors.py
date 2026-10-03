"""Lectures des pros (spec 003)."""

from django.db.models import QuerySet

from jeflink.accounts.models import User

from .models import Provider


def provider_for_owner(user: User) -> Provider | None:
    """Fiche du gérant, quel que soit son statut (un pro suspendu lit encore ses réservations)."""
    return Provider.objects.filter(owner=user).prefetch_related("trades", "zones").first()


def providers_for_admin() -> QuerySet[Provider]:
    return Provider.objects.select_related("owner").prefetch_related("trades", "zones")
