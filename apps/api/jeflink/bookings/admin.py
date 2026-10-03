"""No-shows dans l'admin Django (spec 004) : le groupe « Médiation » confirme ou écarte.

L'Ops joint le client par appel ou WhatsApp avant de trancher (procédure hors de l'admin). Ni
numéro, ni repère, ni position ne s'affichent. La note de contestation du pro est lisible ici
seulement, jamais dans un log ni un audit.
"""

from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest

from jeflink.common.errors import DomainError

from .models import NoShowReport
from .services import decide_no_show


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
