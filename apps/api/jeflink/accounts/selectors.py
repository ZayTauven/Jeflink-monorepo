from django.db.models import QuerySet
from django.utils import timezone

from .models import DeviceSession, RoleGrant, User


def active_roles(user: User) -> set[str]:
    """Rôles stockés actifs. Le rôle client, implicite, n'y figure pas."""
    return set(
        RoleGrant.objects.filter(user=user, revoked_at__isnull=True).values_list("role", flat=True)
    )


def has_role(user: User, *roles: str) -> bool:
    return RoleGrant.objects.filter(user=user, role__in=roles, revoked_at__isnull=True).exists()


def has_group_permission(user: User, app_label: str, codename: str) -> bool:
    """Permission accordée par un groupe Ops. Ignore volontairement ``is_superuser`` (S3)."""
    return user.groups.filter(
        permissions__content_type__app_label=app_label, permissions__codename=codename
    ).exists()


def active_sessions_for(user: User) -> QuerySet[DeviceSession]:
    now = timezone.now()
    return DeviceSession.objects.filter(
        user=user,
        revoked_at__isnull=True,
        idle_expires_at__gt=now,
        absolute_expires_at__gt=now,
    ).order_by("-last_seen_at")
