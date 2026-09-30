"""Écritures du domaine accounts : les autres domaines passent par ici, jamais par les modèles."""

from django.db import transaction
from django.utils import timezone

from jeflink.common.errors import DomainError
from jeflink.trust.models import AuditEvent
from jeflink.trust.services import audit

from .models import Role, RoleGrant, User
from .phone import normalize_phone, phone_display, phone_region
from .validators import clean_display_name

__all__ = [
    "grant_role",
    "normalize_phone",
    "phone_display",
    "phone_region",
    "revoke_role",
    "update_profile",
]


@transaction.atomic
def update_profile(
    *,
    user: User,
    display_name: str | None = None,
    email: str | None = None,
    preferred_language: str | None = None,
) -> User:
    """Mise à jour du profil par son titulaire. ``None`` laisse le champ inchangé.

    Donner un nom fait passer l'invité à complet. Le nom ne peut pas être vidé : un profil
    complet ne redevient jamais invité. L'e-mail est informatif, jamais vérifié ni utilisé
    pour la récupération (S27) ; une chaîne vide l'efface.
    """
    user = User.objects.select_for_update(no_key=True).get(pk=user.pk)
    # Relu sur la ligne verrouillée : une suppression ou une désactivation concurrente gagne.
    if not user.is_active or user.is_deleted:
        raise DomainError("account_disabled", status=403)
    changed: list[str] = []
    if display_name is not None:
        user.display_name = clean_display_name(display_name)
        user.profile_status = User.ProfileStatus.COMPLETE
        changed += ["display_name", "profile_status"]
    if email is not None:
        user.email = User.objects.normalize_email(email.strip())
        changed.append("email")
    if preferred_language is not None:
        if preferred_language not in User.Language.values:
            raise DomainError("language_invalid")
        user.preferred_language = preferred_language
        changed.append("preferred_language")
    if changed:
        user.save(update_fields=[*changed, "updated_at"])
    return user


@transaction.atomic
def grant_role(
    *,
    user: User,
    role: str,
    reason_code: str,
    granted_by: User | None = None,
    operator: str = "",
    second_operator: str = "",
) -> RoleGrant:
    """Accorde un rôle (idempotent). Refusé sur un compte de revue, désactivé ou supprimé."""
    if role not in Role.values:
        raise DomainError("role_unknown")
    # Verrou sur le compte, puis contrôles sur la ligne verrouillée (M1) : deux attributions
    # concurrentes ne créent qu'un RoleGrant, et l'état lu est celui de la base.
    user = User.objects.select_for_update(no_key=True).get(pk=user.pk)
    # Compte de revue des stores (S17) et comptes techniques de l'admin Django (M3).
    if user.is_review_account or user.is_staff or user.is_superuser:
        raise DomainError("role_not_allowed")
    if not user.is_active or user.is_deleted:
        raise DomainError("account_disabled")
    existing = RoleGrant.objects.filter(user=user, role=role, revoked_at__isnull=True).first()
    if existing:
        return existing
    grant = RoleGrant.objects.create(
        user=user, role=role, granted_by=granted_by, reason_code=reason_code
    )
    audit(
        action="accounts.role.granted",
        actor=granted_by,
        actor_kind=_actor_kind(granted_by, operator),
        target=user,
        metadata=_role_metadata(role, reason_code, operator, second_operator),
    )
    return grant


@transaction.atomic
def revoke_role(
    *,
    user: User,
    role: str,
    reason_code: str,
    revoked_by: User | None = None,
    operator: str = "",
    second_operator: str = "",
) -> bool:
    """Retire un rôle actif. Renvoie False s'il n'y en avait pas."""
    updated = RoleGrant.objects.filter(user=user, role=role, revoked_at__isnull=True).update(
        revoked_at=timezone.now(), revoked_by=revoked_by
    )
    if not updated:
        return False
    audit(
        action="accounts.role.revoked",
        actor=revoked_by,
        actor_kind=_actor_kind(revoked_by, operator),
        target=user,
        metadata=_role_metadata(role, reason_code, operator, second_operator),
    )
    return True


def _actor_kind(actor: User | None, operator: str) -> str:
    if actor is not None or operator:
        return AuditEvent.ActorKind.OPS
    return AuditEvent.ActorKind.SYSTEM


def _role_metadata(role: str, reason_code: str, operator: str, second_operator: str) -> dict:
    metadata = {"role": role, "reason_code": reason_code}
    if operator:
        metadata["operator"] = operator
    if second_operator:
        metadata["second_operator"] = second_operator
    return metadata
