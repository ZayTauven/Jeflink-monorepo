from django.contrib import admin

from .models import Trade, Zone


@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "starting_price", "position", "is_active"]
    list_editable = ["position", "is_active"]
    prepopulated_fields = {"slug": ["name"]}


@admin.register(Zone)
class ZoneAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "city", "position", "is_active"]
    list_editable = ["position", "is_active"]
    list_filter = ["city", "is_active"]
    prepopulated_fields = {"slug": ["name"]}
