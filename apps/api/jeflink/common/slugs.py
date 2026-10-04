"""Slugs des données de référence (spec 002) : identifiant public figé, en ASCII sans accent."""

from django.core.validators import RegexValidator
from django.db.models import Q

SLUG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"

validate_reference_slug = RegexValidator(SLUG_PATTERN, code="slug_invalid")


def slug_check(field: str = "slug") -> Q:
    """Condition de ``CheckConstraint`` : le même motif, garanti en base."""
    return Q(**{f"{field}__regex": SLUG_PATTERN})
