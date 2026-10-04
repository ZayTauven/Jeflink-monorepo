"""Saisie Ops des villes et des zones dans l'admin Django (spec 002), carte comprise.

Toute écriture passe par ``zones.services`` ; ni suppression ni changement de slug.
"""

from django import forms
from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin
from django.http import HttpRequest

from jeflink.catalog.admin import ReferenceDataAdmin

from .models import City, Zone
from .services import save_city, save_zone


@admin.register(City)
class CityAdmin(ReferenceDataAdmin):
    list_display = ("name", "slug", "is_active")

    def save_model(self, request: HttpRequest, obj: City, form, change: bool) -> None:
        save_city(city=obj)


@admin.register(Zone)
class ZoneAdmin(ReferenceDataAdmin, GISModelAdmin):
    list_display = ("name", "slug", "city", "radius_m", "position", "is_active", "trade_count")
    list_editable = ("position", "is_active")
    list_filter = ("is_active", "city", "trades")
    search_fields = ("name", "slug")
    fields = (
        "city",
        "slug",
        "name",
        "aliases",
        "center",
        "radius_m",
        "boundary",
        "trades",
        ("position", "is_active"),
    )

    @admin.display(description="métiers ouverts")
    def trade_count(self, obj: Zone) -> int:
        return obj.trades.count()

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == "trades":
            kwargs["widget"] = forms.CheckboxSelectMultiple
        return super().formfield_for_manytomany(db_field, request, **kwargs)

    def save_model(self, request: HttpRequest, obj: Zone, form, change: bool) -> None:
        save_zone(zone=obj)
