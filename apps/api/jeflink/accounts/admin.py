"""Admin Django en lecture seule : les écritures passent par services ou commandes auditées (S3)."""

from django.contrib import admin
from django.contrib.auth.models import Group

from jeflink.common.pii import mask_phone

from .models import RoleGrant, User


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(User)
class UserAdmin(ReadOnlyAdmin):
    list_display = ("public_id", "masked_phone", "profile_status", "is_active", "created_at")
    list_filter = ("profile_status", "is_active", "preferred_language")
    exclude = ("phone", "password", "user_permissions")
    readonly_fields = ("masked_phone",)

    @admin.display(description="téléphone")
    def masked_phone(self, obj: User) -> str:
        return mask_phone(obj.phone) if obj.phone else "—"


@admin.register(RoleGrant)
class RoleGrantAdmin(ReadOnlyAdmin):
    list_display = ("public_id", "role", "reason_code", "created_at", "revoked_at")
    list_filter = ("role",)


# Les groupes portent les permissions Ops : jamais modifiables depuis l'admin (I2).
admin.site.unregister(Group)


@admin.register(Group)
class GroupAdmin(ReadOnlyAdmin):
    list_display = ("name",)
    filter_horizontal = ()
