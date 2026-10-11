from django.contrib import admin

from .models import Quote, RequestEvent, Review, ServiceRequest


class QuoteInline(admin.TabularInline):
    model = Quote
    extra = 0


class EventInline(admin.TabularInline):
    model = RequestEvent
    extra = 0
    can_delete = False
    readonly_fields = ["status", "actor", "note", "created_at"]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ServiceRequest)
class ServiceRequestAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "trade", "zone", "client", "pro", "status", "created_at"]
    list_filter = ["status", "trade", "zone", "is_urgent"]
    search_fields = ["title", "description", "client__email"]
    # Le statut ne se modifie pas à la main : il suit les actions client/pro (jobs.services).
    readonly_fields = ["status", "pro", "created_at", "updated_at"]
    inlines = [QuoteInline, EventInline]


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ["request", "rating", "created_at"]
    list_filter = ["rating"]
