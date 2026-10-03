"""No-shows dans l'admin Django (spec 004) : le groupe « Médiation » confirme ou écarte.

L'Ops joint le client par appel ou WhatsApp avant de trancher (procédure hors de l'admin). Ni
numéro, ni repère, ni position ne s'affichent. La note de contestation du pro est lisible ici
seulement, jamais dans un log ni un audit.
"""

from django import forms
from django.contrib import admin, messages
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponseRedirect
from django.template.response import TemplateResponse

from jeflink.common.errors import DomainError
from jeflink.trust.models import Dispute

from .models import BookingPhoto, NoShowReport
from .services import (
    decide_no_show,
    dispute_photo_links,
    resolve_dispute,
    restore_photo,
)


class FlaggedFilter(admin.SimpleListFilter):
    """No-shows déclarés alors que le pro avait saisi son départ ou son arrivée : à vérifier."""

    title = "pro en route ou sur place"
    parameter_name = "pro_actif"

    def lookups(self, request, model_admin):
        return [("oui", "Départ ou arrivée saisis"), ("non", "Rien saisi")]

    def queryset(self, request: HttpRequest, queryset: QuerySet[NoShowReport]):
        flagged = (
            queryset.filter(booking__en_route_at__isnull=False)
            | queryset.filter(booking__on_site_at__isnull=False)
        ).distinct()
        if self.value() == "oui":
            return flagged
        if self.value() == "non":
            return queryset.exclude(pk__in=flagged.values("pk"))
        return queryset


@admin.register(NoShowReport)
class NoShowReportAdmin(admin.ModelAdmin):
    list_display = ("created_at", "status", "booking_ref", "pro_actif")
    list_filter = ("status", FlaggedFilter)
    readonly_fields = (
        "public_id",
        "booking_ref",
        "status",
        "pro_actif",
        "contest_note",
        "contested_at",
        "decided_by",
        "decided_at",
        "created_at",
    )
    fields = readonly_fields
    actions = ("confirm", "dismiss")

    def get_queryset(self, request: HttpRequest) -> QuerySet[NoShowReport]:
        return super().get_queryset(request).select_related("booking")

    @admin.display(description="Réservation")
    def booking_ref(self, report: NoShowReport) -> str:
        return str(report.booking.public_id)

    @admin.display(description="Départ ou arrivée saisis", boolean=True)
    def pro_actif(self, report: NoShowReport) -> bool:
        return report.booking.en_route_at is not None or report.booking.on_site_at is not None

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_decide_permission(self, request: HttpRequest) -> bool:
        return request.user.has_perm("bookings.decide_noshowreport")

    def get_actions(self, request: HttpRequest):
        return super().get_actions(request) if self.has_decide_permission(request) else {}

    def _decide(self, request: HttpRequest, queryset: QuerySet[NoShowReport], to: str) -> None:
        done = 0
        for report in queryset:
            try:
                decide_no_show(report=report, decision=to, operator=request.user)
                done += 1
            except DomainError as exc:
                self.message_user(
                    request, f"{report.booking.public_id} : {exc.code}", messages.WARNING
                )
        self.message_user(request, f"{done} no-show(s) tranché(s).", messages.SUCCESS)

    @admin.action(description="Confirmer (le pro n'est pas venu)", permissions=("decide",))
    def confirm(self, request: HttpRequest, queryset: QuerySet[NoShowReport]) -> None:
        self._decide(request, queryset, NoShowReport.Status.CONFIRMED)

    @admin.action(description="Écarter (le pro est venu)", permissions=("decide",))
    def dismiss(self, request: HttpRequest, queryset: QuerySet[NoShowReport]) -> None:
        self._decide(request, queryset, NoShowReport.Status.DISMISSED)


# --- Litiges (modèle de ``trust``, enregistré ici : la décision passe par ``bookings``) -----


class ResolveDisputeForm(forms.Form):
    decision = forms.ChoiceField(choices=Dispute.Decision.choices, label="Décision")
    note = forms.CharField(
        max_length=500, widget=forms.Textarea(attrs={"rows": 4}), label="Note de décision"
    )


@admin.register(Dispute)
class DisputeAdmin(admin.ModelAdmin):
    """Le groupe « Médiation » lit le litige (le texte du client y est lisible, nulle part
    ailleurs), voit les photos (consultation auditée) et tranche. Jeflink décide, sans
    remboursement en V1. Ni numéro, ni repère, ni position."""

    list_display = ("created_at", "status", "reason", "decision", "booking_ref")
    list_filter = ("status", "reason", "decision")
    readonly_fields = (
        "public_id",
        "booking_ref",
        "status",
        "reason",
        "description",
        "decision",
        "decision_note",
        "resolved_by",
        "resolved_at",
        "created_at",
    )
    fields = readonly_fields
    actions = ("resolve",)

    def get_queryset(self, request: HttpRequest) -> QuerySet[Dispute]:
        return super().get_queryset(request).select_related("booking")

    @admin.display(description="Réservation")
    def booking_ref(self, dispute: Dispute) -> str:
        return str(dispute.booking.public_id)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_decide_permission(self, request: HttpRequest) -> bool:
        return request.user.has_perm("trust.decide_dispute")

    def get_actions(self, request: HttpRequest):
        return super().get_actions(request) if self.has_decide_permission(request) else {}

    def change_view(self, request: HttpRequest, object_id, form_url="", extra_context=None):
        """Les photos du litige, en URL signées de 10 min ; chaque affichage est audité."""
        extra = dict(extra_context or {})
        dispute = self.get_object(request, object_id)
        if dispute is not None and self.has_view_permission(request, dispute):
            extra["photos"] = dispute_photo_links(dispute=dispute, operator=request.user)
        return super().change_view(request, object_id, form_url, extra)

    @admin.action(description="Trancher", permissions=("decide",))
    def resolve(self, request: HttpRequest, queryset: QuerySet[Dispute]):
        selected = list(queryset.filter(status=Dispute.Status.OPEN))
        if not selected:
            self.message_user(request, "Aucun litige ouvert.", messages.WARNING)
            return None
        if "apply" in request.POST:
            form = ResolveDisputeForm(request.POST)
            if form.is_valid():
                done = 0
                for dispute in selected:
                    try:
                        resolve_dispute(
                            dispute=dispute,
                            decision=form.cleaned_data["decision"],
                            note=form.cleaned_data["note"],
                            operator=request.user,
                        )
                        done += 1
                    except DomainError as exc:
                        self.message_user(
                            request, f"{dispute.booking.public_id} : {exc.code}", messages.WARNING
                        )
                self.message_user(request, f"{done} litige(s) tranché(s).", messages.SUCCESS)
                return HttpResponseRedirect(request.get_full_path())
        else:
            form = ResolveDisputeForm()
        context = {
            **self.admin_site.each_context(request),
            "title": "Trancher un litige",
            "form": form,
            "disputes_selected": selected,
            "action_checkbox_name": ACTION_CHECKBOX_NAME,
            "opts": self.model._meta,
        }
        return TemplateResponse(request, "admin/bookings/resolve_dispute.html", context)


@admin.register(BookingPhoto)
class BookingPhotoAdmin(admin.ModelAdmin):
    """Photos : métadonnées seulement (aucune image ici). L'Ops réaffiche une photo signalée
    quand la réservation a un litige."""

    list_display = ("created_at", "phase", "status", "hidden", "booking_ref")
    list_filter = ("phase", "status")
    readonly_fields = (
        "public_id", "booking_ref", "phase", "status", "width", "height", "size_bytes",
        "hidden_at", "purged_at", "created_at",
    )  # fmt: skip
    fields = readonly_fields
    actions = ("restore",)

    def get_queryset(self, request: HttpRequest) -> QuerySet[BookingPhoto]:
        return super().get_queryset(request).select_related("booking")

    @admin.display(description="Réservation")
    def booking_ref(self, photo: BookingPhoto) -> str:
        return str(photo.booking.public_id)

    @admin.display(description="Signalée", boolean=True)
    def hidden(self, photo: BookingPhoto) -> bool:
        return photo.hidden_at is not None

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_restore_permission(self, request: HttpRequest) -> bool:
        return request.user.has_perm("bookings.restore_bookingphoto")

    def get_actions(self, request: HttpRequest):
        return super().get_actions(request) if self.has_restore_permission(request) else {}

    @admin.action(description="Réafficher", permissions=("restore",))
    def restore(self, request: HttpRequest, queryset: QuerySet[BookingPhoto]) -> None:
        done = 0
        for photo in queryset:
            try:
                restore_photo(photo=photo, operator=request.user)
                done += 1
            except DomainError as exc:
                self.message_user(request, f"{photo.public_id} : {exc.code}", messages.WARNING)
        self.message_user(request, f"{done} photo(s) traitée(s).", messages.SUCCESS)
