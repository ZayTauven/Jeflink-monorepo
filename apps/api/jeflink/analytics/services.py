"""Écritures des mesures (spec 003)."""

from django.db import transaction

from jeflink.common.pii import contains_pii
from jeflink.common.search import normalize

from .models import UnservedDemand

# Motifs de ``zones.selectors.availability`` (sauf ``zone_ambiguous`` : le client choisit, rien
# n'est perdu), plus les deux motifs propres à la demande.
UNSERVED_REASONS = frozenset(
    {
        "trade_not_found",
        "trade_inactive",
        "zone_not_found",
        "zone_inactive",
        "zone_unknown",
        "out_of_area",
        "trade_not_in_zone",
        "no_provider",
        "no_quote",
    }
)
_SLUG_MAX = 50


def _slug_like(value: str | None) -> str:
    """Terme saisi par un client (métier ou quartier inconnu) : normalisé, borné, sans numéro."""
    if not value:
        return ""
    term = normalize(value).replace(" ", "-")[:_SLUG_MAX].strip("-")
    if not term or contains_pii(value) or any(char.isdigit() for char in term):
        return ""
    return term


@transaction.atomic
def record_unserved(
    *,
    reason: str,
    channel: str,
    trade_slug: str | None = None,
    zone_slug: str | None = None,
    zone_text: str = "",
    nearest_zone_slug: str | None = None,
    distance_km: int | None = None,
) -> UnservedDemand:
    """Enregistre un signal « demande non servie », sans aucun identifiant d'utilisateur.

    Les slugs d'un métier ou d'une zone **inconnus** viennent d'un client : on les normalise
    (``trade_not_found``, ``zone_not_found``) et on écarte ce qui contient un chiffre.
    """
    if reason not in UNSERVED_REASONS:
        raise ValueError(f"motif de demande non servie inconnu : {reason}")
    if channel not in UnservedDemand.Channel.values:
        raise ValueError(f"canal inconnu : {channel}")
    if reason == "trade_not_found":
        trade_slug = _slug_like(trade_slug)
    if reason == "zone_not_found":
        zone_slug = _slug_like(zone_slug)
    return UnservedDemand.objects.create(
        reason=reason,
        channel=channel,
        trade_slug=trade_slug or "",
        zone_slug=zone_slug or "",
        # Uniquement pour ``zone_unknown`` : déjà normalisé et sans chiffres par la zone.
        zone_text=zone_text if reason == "zone_unknown" else "",
        nearest_zone_slug=(nearest_zone_slug or "") if reason == "out_of_area" else "",
        distance_km=distance_km if reason == "out_of_area" else None,
    )
