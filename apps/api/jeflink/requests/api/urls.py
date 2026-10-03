from django.urls import path

from . import views

urlpatterns = [
    path("requests/", views.RequestListCreateView.as_view(), name="requests"),
    path("requests/<uuid:public_id>/", views.RequestDetailView.as_view(), name="request-detail"),
    path(
        "requests/<uuid:public_id>/cancel/",
        views.RequestCancelView.as_view(),
        name="request-cancel",
    ),
    path("pro/requests/", views.ProRequestListView.as_view(), name="pro-requests"),
    path(
        "pro/requests/<uuid:public_id>/",
        views.ProRequestDetailView.as_view(),
        name="pro-request-detail",
    ),
    path(
        "pro/requests/<uuid:public_id>/quotes/",
        views.ProQuoteCreateView.as_view(),
        name="pro-request-quote",
    ),
    path("pro/quotes/", views.ProQuoteListView.as_view(), name="pro-quotes"),
    path(
        "pro/quotes/<uuid:public_id>/withdraw/",
        views.ProQuoteWithdrawView.as_view(),
        name="pro-quote-withdraw",
    ),
]
