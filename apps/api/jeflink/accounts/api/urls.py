from django.urls import path

from . import otp_views, views

urlpatterns = [
    path("auth/config/", otp_views.AuthConfigView.as_view(), name="auth-config"),
    path("auth/otp/request/", otp_views.OtpRequestView.as_view(), name="auth-otp-request"),
    path("auth/otp/resend/", otp_views.OtpResendView.as_view(), name="auth-otp-resend"),
    path("auth/otp/verify/", otp_views.OtpVerifyView.as_view(), name="auth-otp-verify"),
    path("auth/token/refresh/", views.TokenRefreshView.as_view(), name="auth-token-refresh"),
    path("auth/logout/", views.LogoutView.as_view(), name="auth-logout"),
    path("me/", views.MeView.as_view(), name="me"),
    path("me/invitations/", views.MyInvitationsView.as_view(), name="me-invitations"),
    path(
        "me/invitations/<uuid:public_id>/accept/",
        views.AcceptInvitationView.as_view(),
        name="me-invitation-accept",
    ),
    path(
        "me/invitations/<uuid:public_id>/decline/",
        views.DeclineInvitationView.as_view(),
        name="me-invitation-decline",
    ),
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
