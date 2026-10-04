"""Saisie Ops du catalogue dans l'admin Django (spec 002) : on modifie, on ne supprime jamais.

Toute écriture passe par ``catalog.services`` ; le slug est figé après création.
"""

from django import forms
from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest

from jeflink.zones.services import open_trade_in_all_zones

from .models import Service, Trade
from .services import save_service, save_trade


class MissingWolofFilter(admin.SimpleListFilter):
    title = "libellé wo"
    parameter_name = "wo"

    def lookups(self, request, model_admin):
        return [("vide", "wo vide")]

    def queryset(self, request, queryset):
        if self.value() == "vide":
            return queryset.filter(name_wo="")
        return queryset


class ReferenceDataAdmin(admin.ModelAdmin):
    """Ni suppression ni changement de slug : on désactive (spec 002)."""

    def has_delete_permission(self, request, obj=None) -> bool:
        return False

    def get_readonly_fields(self, request, obj=None):
        readonly = tuple(super().get_readonly_fields(request, obj))
        return (*readonly, "slug") if obj is not None else readonly


class FrozenSlugForm(forms.ModelForm):
    """Le slug d'une ligne déjà enregistrée est affiché mais jamais repris du formulaire."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk is not None and "slug" in self.fields:
            self.fields["slug"].disabled = True


class ServiceInline(admin.TabularInline):
    model = Service
    form = FrozenSlugForm
    extra = 0
    can_delete = False
    fields = (
        "slug",
        "name_fr",
        "name_wo",
        "aliases",
        "price_from_xof",
        "urgent",
        "is_active",
        "position",
    )

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(Trade)
class TradeAdmin(ReferenceDataAdmin):
    list_display = ("name_fr", "slug", "is_active", "position", "service_count")
    list_editable = ("is_active", "position")
    list_filter = ("is_active", MissingWolofFilter)
    search_fields = ("name_fr", "slug")
    inlines = (ServiceInline,)
    actions = ("open_everywhere",)
    fields = (
        "slug",
        ("name_fr", "name_wo"),
        ("short_description_fr", "short_description_wo"),
        ("seo_title_fr", "seo_title_wo"),
        "aliases",
        "icon_key",
        ("is_active", "position"),
    )

    @admin.display(description="services")
    def service_count(self, obj: Trade) -> int:
        return obj.services.count()

    def save_model(self, request: HttpRequest, obj: Trade, form, change: bool) -> None:
        save_trade(trade=obj)

    def save_formset(self, request: HttpRequest, form, formset, change: bool) -> None:
        for service in formset.save(commit=False):
            save_service(service=service)

    @admin.action(description="Ouvrir dans toutes les zones actives")
    def open_everywhere(self, request: HttpRequest, queryset: QuerySet[Trade]) -> None:
        added = sum(open_trade_in_all_zones(trade=trade) for trade in queryset)
        self.message_user(request, f"{added} ouverture(s) ajoutée(s).", messages.SUCCESS)
