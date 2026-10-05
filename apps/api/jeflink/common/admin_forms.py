"""Pages d'argent de l'admin Django (spec 005) : une action avec page intermédiaire, ou un
formulaire de saisie, toutes deux derrière ``StepUpForm`` (code TOTP frais). Les erreurs métier
sont traduites par le dictionnaire de libellés de l'admin appelant."""

from collections.abc import Callable, Mapping

from django.contrib import messages
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse

from jeflink.common.errors import DomainError


def error_label(exc: DomainError, labels: Mapping[str, str]) -> str:
    return labels.get(exc.code, exc.code)


def action_page(
    modeladmin,
    request: HttpRequest,
    selected: list,
    *,
    action: str,
    title: str,
    form_class,
    apply: Callable[[object, dict], None],
    labels: Mapping[str, str],
    intro: str = "",
) -> HttpResponse:
    """Action de liste : page intermédiaire avec le formulaire, puis ``apply(objet, données)``
    pour chaque objet sélectionné. Une erreur métier sur un objet n'arrête pas les autres."""
    if "apply" in request.POST:
        form = form_class(request.POST, request=request)
        if form.is_valid():
            done = 0
            for obj in selected:
                try:
                    apply(obj, form.cleaned_data)
                    done += 1
                except DomainError as exc:
                    modeladmin.message_user(
                        request, f"{obj} : {error_label(exc, labels)}", messages.WARNING
                    )
            modeladmin.message_user(request, f"{done} élément(s) traité(s).", messages.SUCCESS)
            return HttpResponseRedirect(request.get_full_path())
    else:
        form = form_class(request=request)
    context = {
        **modeladmin.admin_site.each_context(request),
        "title": title,
        "intro": intro,
        "form": form,
        "selected": selected,
        "action": action,
        "action_checkbox_name": ACTION_CHECKBOX_NAME,
        "opts": modeladmin.model._meta,
    }
    return TemplateResponse(request, "admin/jeflink/action_form.html", context)


def form_page(
    modeladmin,
    request: HttpRequest,
    *,
    title: str,
    form_class,
    initial: dict,
    submit: Callable[[dict], str],
    success_url: str,
    labels: Mapping[str, str],
    intro: str = "",
) -> HttpResponse:
    """Formulaire de saisie : ``submit(données)`` rend le message de réussite."""
    if request.method == "POST":
        form = form_class(request.POST, request=request)
        if form.is_valid():
            try:
                message = submit(form.cleaned_data)
            except DomainError as exc:
                form.add_error(None, error_label(exc, labels))
            else:
                modeladmin.message_user(request, message, messages.SUCCESS)
                return HttpResponseRedirect(success_url)
    else:
        form = form_class(request=request, initial=initial)
    context = {
        **modeladmin.admin_site.each_context(request),
        "title": title,
        "intro": intro,
        "form": form,
        "opts": modeladmin.model._meta,
    }
    return TemplateResponse(request, "admin/jeflink/form_page.html", context)
