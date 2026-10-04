"""Avis dans l'admin Django (spec 004) : le groupe « Modération avis » masque ou réaffiche, sans
jamais supprimer. Le commentaire est lisible ici seulement ; ni numéro, ni nom du client."""

from django import forms
from django.contrib import admin, messages
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponseRedirect
from django.template.response import TemplateResponse

from jeflink.common.errors import DomainError

from .models import HIDE_REASONS, Review
from .services import hide_review, restore_review


class HideReviewForm(forms.Form):
    reason = forms.ChoiceField(choices=[(code, code) for code in HIDE_REASONS], label="Motif")


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("created_at", "rating", "published", "hidden", "provider")
    list_filter = ("rating", "hidden_reason")
    readonly_fields = (
        "public_id", "provider", "rating", "tags", "comment", "published_at", "edited_at",
        "hidden_at", "hidden_reason", "hidden_by", "created_at",
    )  # fmt: skip
    fields = readonly_fields
    actions = ("hide", "restore")

    def get_queryset(self, request: HttpRequest) -> QuerySet[Review]:
        return super().get_queryset(request).select_related("provider")

    @admin.display(description="Publié", boolean=True)
    def published(self, review: Review) -> bool:
        return review.published_at is not None

    @admin.display(description="Masqué", boolean=True)
    def hidden(self, review: Review) -> bool:
        return review.hidden_at is not None

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_moderate_permission(self, request: HttpRequest) -> bool:
        return request.user.has_perm("reviews.moderate_review")

    def get_actions(self, request: HttpRequest):
        return super().get_actions(request) if self.has_moderate_permission(request) else {}

    @admin.action(description="Masquer", permissions=("moderate",))
    def hide(self, request: HttpRequest, queryset: QuerySet[Review]):
        selected = list(queryset)
        if "apply" in request.POST:
            form = HideReviewForm(request.POST)
            if form.is_valid():
                done = 0
                for review in selected:
                    try:
                        hide_review(
                            review=review, reason=form.cleaned_data["reason"], operator=request.user
                        )
                        done += 1
                    except DomainError as exc:
                        self.message_user(
                            request, f"{review.public_id} : {exc.code}", messages.WARNING
                        )
                self.message_user(request, f"{done} avis masqué(s).", messages.SUCCESS)
                return HttpResponseRedirect(request.get_full_path())
        else:
            form = HideReviewForm()
        context = {
            **self.admin_site.each_context(request),
            "title": "Masquer des avis",
            "form": form,
            "reviews_selected": selected,
            "action_checkbox_name": ACTION_CHECKBOX_NAME,
            "opts": self.model._meta,
        }
        return TemplateResponse(request, "admin/reviews/hide_review.html", context)

    @admin.action(description="Réafficher", permissions=("moderate",))
    def restore(self, request: HttpRequest, queryset: QuerySet[Review]) -> None:
        for review in queryset:
            restore_review(review=review, operator=request.user)
        self.message_user(request, f"{queryset.count()} avis réaffiché(s).", messages.SUCCESS)
