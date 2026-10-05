from django.urls import path

from . import views

urlpatterns = [
    path("pro/wallet/", views.WalletSummaryView.as_view(), name="pro-wallet"),
    path("pro/wallet/entries/", views.WalletEntryListView.as_view(), name="pro-wallet-entries"),
    path(
        "pro/wallet/entries/<uuid:public_id>/",
        views.WalletEntryDetailView.as_view(),
        name="pro-wallet-entry",
    ),
    path(
        "pro/wallet/settlements/",
        views.SettlementListCreateView.as_view(),
        name="pro-wallet-settlements",
    ),
    path(
        "pro/wallet/settlements/<uuid:public_id>/correct/",
        views.SettlementCorrectView.as_view(),
        name="pro-wallet-settlement-correct",
    ),
    path(
        "pro/wallet/settlements/<uuid:public_id>/cancel/",
        views.SettlementCancelView.as_view(),
        name="pro-wallet-settlement-cancel",
    ),
]
