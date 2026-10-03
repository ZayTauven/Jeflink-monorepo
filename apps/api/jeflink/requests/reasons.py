"""Motifs d'annulation et notes (spec 003). Codes en dur : ils pilotent la fiabilité du pro,
contrairement aux libellés de données (ADR 0009). Les fronts les traduisent en clés i18n."""

from jeflink.common.errors import DomainError
from jeflink.common.pii import contains_pii

CLIENT_REASONS = ("changed_mind", "found_other", "price", "unavailable", "other")
PRO_REASONS = ("unavailable", "too_far", "job_mismatch", "other")
SYSTEM_REASONS = ("pro_unconfirmed", "provider_suspended")
NOTE_MAX_LENGTH = 200


def clean_note(note: str | None) -> str:
    """Note libre : bornée, sans numéro de téléphone (le contournement ne passe pas par là)."""
    text = " ".join((note or "").split())
    if len(text) > NOTE_MAX_LENGTH or contains_pii(text):
        raise DomainError("note_invalid", status=422)
    return text


def check_reason(reason: str, *, allowed: tuple[str, ...], note: str | None) -> str:
    """Valide le motif et sa note. ``other`` exige une note. Renvoie la note nettoyée."""
    if reason not in allowed:
        raise DomainError("reason_invalid", status=422)
    cleaned = clean_note(note)
    if reason == "other" and not cleaned:
        raise DomainError("note_invalid", status=422)
    return cleaned
