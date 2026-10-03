"""I1 (revue sécurité tâche 8) : toute vue authentifiée refuse une session restreinte (compte
dormant, S18), sauf une liste blanche explicite de couples (vue, méthode)."""

import pytest
from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

# Couples admis pour une session restreinte : se déconnecter doit toujours rester possible,
# l'app lit un profil minimal pour choisir l'écran du compte dormant, et le client peut
# « Repartir de zéro » (tâche 14).
RESTRICTED_ALLOWED = {("LogoutView", "POST"), ("MeView", "GET"), ("FreshStartView", "POST")}
METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")


def _walk(patterns):
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            yield from _walk(pattern.url_patterns)
        elif isinstance(pattern, URLPattern):
            yield pattern


def _api_views():
    for pattern in _walk(get_resolver().url_patterns):
        view_class = getattr(pattern.callback, "view_class", None) or getattr(
            pattern.callback, "cls", None
        )
        if view_class is not None and hasattr(view_class, "get_permissions"):
            yield view_class


def _permissions(view_class, request):
    """Permissions réelles de la vue pour cette méthode (``get_permissions`` compris)."""
    view = view_class()
    view.request = request
    view.args, view.kwargs = (), {}
    view.format_kwarg = None
    return view.get_permissions()


@pytest.mark.django_db
def test_sessions_restreintes_refusees_hors_liste_blanche(user_factory):
    user = user_factory()
    claims = {"restricted": True, "sid": "x", "sub": str(user.public_id)}

    checked = set()
    for view_class in _api_views():
        name = view_class.__name__
        for method in METHODS:
            if not hasattr(view_class, method.lower()):
                continue
            request = Request(APIRequestFactory().generic(method, "/"))
            request.user = user
            request.auth = claims
            permissions = _permissions(view_class, request)
            if any(isinstance(p, AllowAny) for p in permissions):
                continue  # vue publique : couverte par le test S29 (limites par IP)
            allowed = all(p.has_permission(request, None) for p in permissions)
            checked.add((name, method))
            if (name, method) in RESTRICTED_ALLOWED:
                assert allowed, f"{name} {method} doit rester accessible à une session restreinte"
            else:
                assert not allowed, f"{name} {method} laisse passer une session restreinte"
    assert RESTRICTED_ALLOWED | {("MySessionsView", "GET"), ("MeView", "PATCH")} <= checked
