"""Demandes dans l'admin Django (spec 003) : l'Ops rattache à une zone une demande au quartier
inconnu. Ni repère, ni position, ni description, ni client ne s'affichent (minimisation)."""

from django import forms
from django.contrib import admin, messages
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse

from jeflink.common.errors import DomainError
from jeflink.zones.selectors import active_zones

from .models import ServiceRequest
from .services import attach_zone


class AttachZoneForm(forms.Form):
    zone = forms.ModelChoiceField(queryset=None, label="Zone")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["zone"].queryset = active_zones()


@admin.register(ServiceRequest)
class ServiceRequestAdmin(admin.ModelAdmin):
    list_display = ("created_at", "status", "trade", "zone", "zone_text", "urgent", "channel")
    list_filter = ("status", "trade", "channel")
    readonly_fields = (
        "public_id",
        "status",
        "trade",
        "service",
        "zone",
        "zone_text",
        "urgent",
        "channel",
        "created_at",
        "expires_at",
    )
    fields = readonly_fields
    actions = ("attach_to_zone",)

    def get_queryset(self, request: HttpRequest) -> QuerySet[ServiceRequest]:
        # defer : le repère, la position et la description ne sortent jamais dans l'admin.
        return (
            super()
            .get_queryset(request)
            .select_related("trade", "service", "zone")
            .defer("landmark", "location", "description")
        )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_attach_permission(self, request: HttpRequest) -> bool:
        return request.user.has_perm("requests.attach_servicerequest")

    def get_actions(self, request: HttpRequest):
        return super().get_actions(request) if self.has_attach_permission(request) else {}

    @admin.action(description="Rattacher à une zone", permissions=("attach",))
    def attach_to_zone(
        self, request: HttpRequest, queryset: QuerySet[ServiceRequest]
    ) -> HttpResponse | None:
        selected = list(queryset.filter(status=ServiceRequest.Status.NEEDS_ZONE))
        if not selected:
            self.message_user(request, "Aucune demande « quartier à vérifier ».", messages.WARNING)
            return None
        if "apply" in request.POST:
            form = AttachZoneForm(request.POST)
            if form.is_valid():
                zone = form.cleaned_data["zone"]
                done = 0
                for item in selected:
                    try:
                        attach_zone(request=item, zone=zone, operator=request.user)
                        done += 1
                    except DomainError as exc:
                        self.message_user(
                            request, f"{item.public_id} : {exc.code}", messages.WARNING
                        )
                self.message_user(request, f"{done} demande(s) rattachée(s).", messages.SUCCESS)
                return HttpResponseRedirect(request.get_full_path())
        else:
            form = AttachZoneForm()
        context = {
            **self.admin_site.each_context(request),
            "title": "Rattacher à une zone",
            "form": form,
            "requests_selected": selected,
            "action_checkbox_name": ACTION_CHECKBOX_NAME,
            "opts": self.model._meta,
        }
        return TemplateResponse(request, "admin/requests/attach_zone.html", context)
