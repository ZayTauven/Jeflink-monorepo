"""Lectures des pros (spec 003)."""

from django.db.models import Count, Q, QuerySet

from jeflink.accounts.models import User
from jeflink.catalog.models import Trade
from jeflink.zones.models import Zone

from .models import Provider


def provider_for_owner(user: User) -> Provider | None:
    """Fiche du gérant, quel que soit son statut (un pro suspendu lit encore ses réservations)."""
    return Provider.objects.filter(owner=user).prefetch_related("trades", "zones").first()


def public_verified_providers(
    *, trade: Trade | None = None, zone: Zone | None = None
) -> QuerySet[Provider]:
    """Fiches vérifiées qui peuvent être comptées en public (spec 006) : ni démo, ni compte de
    revue. Métier et quartier sont ceux de la fiche. Pour un compte seulement."""
    providers = Provider.objects.filter(
        status=Provider.Status.VERIFIED, is_demo=False, owner__is_review_account=False
    )
    if trade is not None:
        providers = providers.filter(trades=trade)
    if zone is not None:
        providers = providers.filter(zones=zone)
    return providers


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
