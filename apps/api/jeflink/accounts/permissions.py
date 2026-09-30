"""Classes de permission DRF du domaine accounts (spec 001, « Rôles et permissions »).

Ce sont des classes de rôle : elles ne contrôlent aucun objet. Les listes sont toujours
filtrées par un sélecteur qui prend ``user`` ; un objet d'un autre utilisateur renvoie 404 (S5).
"""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from django.utils import timezone
from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from .models import Role
from .selectors import has_group_permission, has_role

STEP_UP_MAX_AGE = timedelta(minutes=5)
# Tolérance d'horloge : un horodatage plus loin dans le futur est refusé (M5).
CLOCK_SKEW = timedelta(seconds=60)


def token_claims(request: Request) -> Mapping[str, Any]:
    """Claims du jeton d'accès (``request.auth``), ou vide hors authentification JWT."""
    auth = request.auth
    if isinstance(auth, Mapping):
        return auth
    payload = getattr(auth, "payload", None)
    return payload if isinstance(payload, Mapping) else {}


def _claim_age(request: Request, claim: str) -> timedelta | None:
    value = token_claims(request).get(claim)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    try:
        age = timezone.now() - datetime.fromtimestamp(value, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None
    return None if age < -CLOCK_SKEW else age


class IsClient(BasePermission):
    """Authentifié, actif, non supprimé, session non restreinte. Tout compte est client.

    - Les comptes techniques de l'admin Django (staff, superutilisateur) n'utilisent jamais
      l'API (S3, défense en profondeur).
    - Une session restreinte (compte dormant, S18) est refusée **par défaut** : toutes les
      permissions en héritent. Seule ``AllowRestrictedSession`` l'admet, sur une liste
      blanche de vues (déconnexion, choix du compte dormant, profil minimal).
    """

    code = "not_authenticated"
    message = "not_authenticated"
    allow_restricted = False

    def has_permission(self, request: Request, view: Any) -> bool:
        user = request.user
        if not (
            user
            and user.is_authenticated
            and user.is_active
            and user.deleted_at is None
            and not user.is_staff
            and not user.is_superuser
        ):
            return False
        if not self.allow_restricted and token_claims(request).get("restricted", False):
            self.code = self.message = "session_restricted"
            return False
        return True


class AllowRestrictedSession(IsClient):
    """Admet une session restreinte. Réservée à la liste blanche testée (déconnexion…)."""

    allow_restricted = True


class RequiresCompleteProfile(IsClient):
    code = "profile_incomplete"
    message = "profile_incomplete"

    def has_permission(self, request: Request, view: Any) -> bool:
        return super().has_permission(request, view) and request.user.profile_status == "complete"


def RequiresRecentAuth(max_age: timedelta) -> type[BasePermission]:
    """Exige un OTP ou TOTP récent (claim ``auth_time``), sinon ``403 reauth_required``."""

    class _RequiresRecentAuth(IsClient):
        code = "reauth_required"
        message = "reauth_required"

        def has_permission(self, request: Request, view: Any) -> bool:
            if not super().has_permission(request, view):
                return False
            age = _claim_age(request, "auth_time")
            return age is not None and age <= max_age

    return _RequiresRecentAuth


class HasOwnerRole(IsClient):
    code = "role_required"
    message = "role_required"

    def has_permission(self, request: Request, view: Any) -> bool:
        return super().has_permission(request, view) and has_role(request.user, Role.OWNER)


class HasTechnicianRole(IsClient):
    """Technicien, ou gérant : l'artisan solo est son propre technicien (ADR 0003)."""

    code = "role_required"
    message = "role_required"

    def has_permission(self, request: Request, view: Any) -> bool:
        return super().has_permission(request, view) and has_role(
            request.user, Role.TECHNICIAN, Role.OWNER
        )


def HasOpsPerm(perm: str, *, step_up: bool) -> type[BasePermission]:
    """``HasOpsPerm("ops.accounts.view", step_up=False)`` : rôle ops, second facteur, groupe.

    ``step_up=True`` exige en plus un TOTP de moins de 5 min. Le choix est explicite à chaque
    usage (M4). Ne s'appuie jamais sur ``is_superuser`` (S3).
    """
    prefix, app_label, action = perm.split(".", 2)
    if prefix != "ops":
        raise ValueError(f"permission Ops attendue : {perm}")
    codename = f"ops_{app_label}_{action}"
    needs_step_up = step_up

    class _HasOpsPerm(IsClient):
        code = "ops_forbidden"
        message = "ops_forbidden"

        def has_permission(self, request: Request, view: Any) -> bool:
            self.code = self.message = "ops_forbidden"
            if not super().has_permission(request, view):
                return False
            if token_claims(request).get("mfa") is not True:
                return False
            if not has_role(request.user, Role.OPS):
                return False
            if not has_group_permission(request.user, app_label, codename):
                return False
            if needs_step_up:
                age = _claim_age(request, "mfa_at")
                if age is None or age > STEP_UP_MAX_AGE:
                    self.code = self.message = "ops_step_up_required"
                    return False
            return True

    _HasOpsPerm.__name__ = f"HasOpsPerm_{codename}"
    return _HasOpsPerm


class _DenyByDefault(BasePermission):
    """Réservé aux classes objet de providers et bookings : refuse tant qu'elles n'existent pas."""

    def has_permission(self, request: Request, view: Any) -> bool:
        return False

    def has_object_permission(self, request: Request, view: Any, obj: Any) -> bool:
        return False


class IsProOwner(_DenyByDefault):
    pass


class IsTechnicianAssigned(_DenyByDefault):
    pass
