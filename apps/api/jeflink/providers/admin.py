"""Fiches pro dans l'admin Django (spec 003) : lecture, et deux actions pour le groupe
« Validation pros ». Création par ``manage.py onboard_provider`` ; aucune édition libre."""

from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest

from jeflink.common.errors import DomainError

from .models import Provider
from .selectors import providers_for_admin
from .services import set_status


@admin.register(Provider)
class ProviderAdmin(admin.ModelAdmin):
    list_display = ("business_name", "status", "masked_numbers_count", "is_demo", "created_at")
    list_filter = ("status", "is_demo", "trades")
    search_fields = ("business_name",)
    readonly_fields = (
        "public_id",
        "business_name",
        "status",
        "status_changed_at",
        "masked_numbers_count",
        "is_demo",
        "trades",
        "zones",
        "created_at",
    )
    fields = readonly_fields
    actions = ("verify", "suspend")

    def get_queryset(self, request: HttpRequest) -> QuerySet[Provider]:
        return providers_for_admin()

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_verify_permission(self, request: HttpRequest) -> bool:
        return request.user.has_perm("providers.verify_provider")

    def get_actions(self, request: HttpRequest):
        actions = super().get_actions(request)
        if not self.has_verify_permission(request):
            return {}
        return actions

    def _apply(self, request: HttpRequest, queryset: QuerySet[Provider], to: str) -> None:
        done = 0
        for provider in queryset:
            try:
                set_status(provider=provider, to=to, actor=request.user)
                done += 1
            except DomainError as exc:
                self.message_user(
                    request, f"{provider.business_name} : {exc.code}", messages.WARNING
                )
        self.message_user(request, f"{done} fiche(s) mise(s) à jour.", messages.SUCCESS)

    @admin.action(description="Vérifier", permissions=("verify",))
    def verify(self, request: HttpRequest, queryset: QuerySet[Provider]) -> None:
        self._apply(request, queryset, Provider.Status.VERIFIED)

    @admin.action(description="Suspendre", permissions=("verify",))
    def suspend(self, request: HttpRequest, queryset: QuerySet[Provider]) -> None:
        self._apply(request, queryset, Provider.Status.SUSPENDED)
