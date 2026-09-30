from django.urls import path

from . import views

urlpatterns = [
    path("auth/token/refresh/", views.TokenRefreshView.as_view(), name="auth-token-refresh"),
    path("auth/logout/", views.LogoutView.as_view(), name="auth-logout"),
    path("me/sessions/", views.MySessionsView.as_view(), name="me-sessions"),
    path(
        "me/sessions/revoke-others/",
        views.RevokeOtherSessionsView.as_view(),
        name="me-sessions-revoke-others",
    ),
    path(
        "me/sessions/<uuid:public_id>/",
        views.MySessionDetailView.as_view(),
        name="me-session-detail",
    ),
]
