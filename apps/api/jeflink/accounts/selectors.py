from typing import Any

from django.db.models import Exists, OuterRef, QuerySet
from django.utils import timezone

from .models import DeviceSession, Role, RoleGrant, RoleInvitation, User
from .phone import phone_display


def active_roles(user: User) -> set[str]:
    """Rôles stockés actifs. Le rôle client, implicite, n'y figure pas."""
    return set(
        RoleGrant.objects.filter(user=user, revoked_at__isnull=True).values_list("role", flat=True)
    )


def account_profile(user: User, *, restricted: bool) -> dict[str, Any]:
    """Profil du compte vu par son titulaire (``GET /api/me/``, réponse de ``otp/verify``).

    Session restreinte (compte dormant, numéro peut-être recyclé) : rien de l'ancien titulaire,
    seulement le numéro que la session vient de prouver et le type d'écran à afficher (I2).
    """
    roles = sorted(active_roles(user))
    profile: dict[str, Any] = {
        "public_id": user.public_id,
        "phone": user.phone,
        "phone_display": phone_display(user.phone),
        "restricted": restricted,
    }
    if restricted:
        is_pro = bool({Role.OWNER, Role.TECHNICIAN} & set(roles))
        return {
            **profile,
            "display_name": "",
            "email": "",
            "preferred_language": User.Language.FR,
            "profile_status": User.ProfileStatus.GUEST,
            "roles": [],
            "created_at": None,
            "restriction_kind": "pro" if is_pro else "client",
        }
    return {
        **profile,
        "display_name": user.display_name,
        "email": user.email,
        "preferred_language": user.preferred_language,
        "profile_status": user.profile_status,
        "roles": roles,
        "created_at": user.created_at,
        "restriction_kind": None,
    }


def has_role(user: User, *roles: str) -> bool:
    return RoleGrant.objects.filter(user=user, role__in=roles, revoked_at__isnull=True).exists()


def has_group_permission(user: User, app_label: str, codename: str) -> bool:
    """Permission accordée par un groupe Ops. Ignore volontairement ``is_superuser`` (S3)."""
    return user.groups.filter(
        permissions__content_type__app_label=app_label, permissions__codename=codename
    ).exists()


def pending_invitations_for(user: User) -> QuerySet[RoleInvitation]:
    """Invitations en attente pour le numéro du compte, d'un gérant toujours actif (revue, I1)."""
    # Compte de revue des stores : aucune invitation d'un vrai pro ne lui est montrée (M5).
    if not user.phone or user.is_review_account:
        return RoleInvitation.objects.none()
    inviter_is_owner = RoleGrant.objects.filter(
        user=OuterRef("invited_by"), role=Role.OWNER, revoked_at__isnull=True
    )
    return (
        RoleInvitation.objects.filter(
            Exists(inviter_is_owner),
            phone=user.phone,
            status=RoleInvitation.Status.PENDING,
            expires_at__gt=timezone.now(),
            invited_by__is_active=True,
            invited_by__deleted_at__isnull=True,
        )
        .select_related("invited_by")
        .order_by("-created_at")
    )


def active_sessions_for(user: User) -> QuerySet[DeviceSession]:
    now = timezone.now()
    return DeviceSession.objects.filter(
        user=user,
        revoked_at__isnull=True,
        idle_expires_at__gt=now,
        absolute_expires_at__gt=now,
    ).order_by("-last_seen_at")
