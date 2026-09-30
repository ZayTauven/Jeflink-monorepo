"""I1 (revue sécurité tâche 8) : toute vue authentifiée refuse une session restreinte (compte
dormant, S18), sauf une liste blanche explicite."""

import pytest
from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

# Vues admises pour une session restreinte : se déconnecter doit toujours rester possible.
# L'écran de choix du compte dormant et le profil minimal s'y ajouteront (tâches 11 et 14).
RESTRICTED_ALLOWED = {"LogoutView"}


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
        if view_class is not None and hasattr(view_class, "permission_classes"):
            yield view_class


@pytest.mark.django_db
def test_sessions_restreintes_refusees_hors_liste_blanche(user_factory):
    user = user_factory()
    request = Request(APIRequestFactory().get("/"))
    request.user = user
    request.auth = {"restricted": True, "sid": "x", "sub": str(user.public_id)}

    checked = []
    for view_class in _api_views():
        permissions = [p() for p in view_class.permission_classes]
        if any(isinstance(p, AllowAny) for p in permissions):
            continue  # vue publique : couverte par le test S29 (limites par IP)
        allowed = all(p.has_permission(request, None) for p in permissions)
        name = view_class.__name__
        checked.append(name)
        if name in RESTRICTED_ALLOWED:
            assert allowed, f"{name} doit rester accessible à une session restreinte"
        else:
            assert not allowed, f"{name} laisse passer une session restreinte"
    assert {"MySessionsView", "LogoutView"} <= set(checked)
