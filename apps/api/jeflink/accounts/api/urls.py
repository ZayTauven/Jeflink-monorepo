from django.urls import path

from . import deletion_views, mfa_views, ops_views, otp_views, phone_change_views, views

urlpatterns = [
    path("auth/config/", otp_views.AuthConfigView.as_view(), name="auth-config"),
    path("auth/otp/request/", otp_views.OtpRequestView.as_view(), name="auth-otp-request"),
    path("auth/otp/resend/", otp_views.OtpResendView.as_view(), name="auth-otp-resend"),
    path("auth/otp/verify/", otp_views.OtpVerifyView.as_view(), name="auth-otp-verify"),
    path("auth/mfa/totp/setup/", mfa_views.TotpSetupView.as_view(), name="auth-mfa-setup"),
    path("auth/mfa/totp/confirm/", mfa_views.TotpConfirmView.as_view(), name="auth-mfa-confirm"),
    path("auth/mfa/totp/verify/", mfa_views.TotpVerifyView.as_view(), name="auth-mfa-verify"),
    path("auth/mfa/totp/step-up/", mfa_views.TotpStepUpView.as_view(), name="auth-mfa-step-up"),
    path("auth/token/refresh/", views.TokenRefreshView.as_view(), name="auth-token-refresh"),
    path("auth/logout/", views.LogoutView.as_view(), name="auth-logout"),
    path("me/", views.MeView.as_view(), name="me"),
    path(
        "auth/phone-change/confirm/",
        phone_change_views.PhoneChangeConfirmView.as_view(),
        name="auth-phone-change-confirm",
    ),
    path(
        "ops/accounts/<uuid:public_id>/phone-change/",
        phone_change_views.PhoneChangeCreateView.as_view(),
        name="ops-phone-change",
    ),
    path(
        "ops/phone-changes/",
        phone_change_views.PhoneChangeListView.as_view(),
        name="ops-phone-changes",
    ),
    *[
        path(f"ops/phone-changes/<uuid:public_id>/{slug}/", view.as_view(), name=f"ops-pc-{slug}")
        for slug, view in (
            ("approve", phone_change_views.PhoneChangeApproveView),
            ("reject", phone_change_views.PhoneChangeRejectView),
            ("resend-code", phone_change_views.PhoneChangeResendView),
        )
    ],
    path("ops/accounts/search/", ops_views.OpsAccountSearchView.as_view(), name="ops-search"),
    path(
        "ops/accounts/<uuid:public_id>/",
        ops_views.OpsAccountDetailView.as_view(),
        name="ops-account",
    ),
    *[
        path(f"ops/accounts/<uuid:public_id>/{slug}/", view.as_view(), name=f"ops-{slug}")
        for slug, view in (
            ("reveal-phone", ops_views.OpsRevealPhoneView),
            ("revoke-sessions", ops_views.OpsRevokeSessionsView),
            ("unblock-otp", ops_views.OpsUnblockOtpView),
            ("deactivate", ops_views.OpsDeactivateView),
            ("reactivate", ops_views.OpsReactivateView),
            ("clear-dormant", ops_views.OpsClearDormantView),
        )
    ],
    path("me/deletion/otp/", deletion_views.DeletionOtpView.as_view(), name="me-deletion-otp"),
    path("me/deletion/", deletion_views.DeletionView.as_view(), name="me-deletion"),
    path("me/fresh-start/", deletion_views.FreshStartView.as_view(), name="me-fresh-start"),
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
