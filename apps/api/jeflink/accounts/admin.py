from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import ProProfile, User


class ProProfileInline(admin.StackedInline):
    model = ProProfile
    can_delete = False
    filter_horizontal = ["trades", "zones"]


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ["email"]
    list_display = ["email", "first_name", "last_name", "role", "phone", "is_staff"]
    list_filter = ["role", "is_staff", "is_active"]
    search_fields = ["email", "first_name", "last_name", "phone"]
    fieldsets = [
        (None, {"fields": ["email", "password"]}),
        ("Identité", {"fields": ["first_name", "last_name", "phone", "role"]}),
        ("Droits", {"fields": ["is_active", "is_staff", "is_superuser", "groups"]}),
        ("Dates", {"fields": ["last_login", "date_joined"]}),
    ]
    add_fieldsets = [
        (None, {"classes": ["wide"], "fields": ["email", "role", "password1", "password2"]}),
    ]

    def get_inlines(self, request, obj):
        return [ProProfileInline] if obj and obj.is_pro else []


@admin.register(ProProfile)
class ProProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "headline", "years_experience", "is_verified"]
    list_editable = ["is_verified"]
    list_filter = ["is_verified", "trades"]
    filter_horizontal = ["trades", "zones"]
    search_fields = ["user__email", "user__first_name", "user__last_name"]
