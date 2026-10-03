from django.urls import path

from . import views

urlpatterns = [
    path("quotes/<uuid:public_id>/accept/", views.AcceptQuoteView.as_view(), name="quote-accept"),
    path("bookings/", views.BookingListView.as_view(), name="bookings"),
    path("bookings/<uuid:public_id>/", views.BookingDetailView.as_view(), name="booking-detail"),
    path(
        "bookings/<uuid:public_id>/cancel/",
        views.BookingCancelView.as_view(),
        name="booking-cancel",
    ),
    path("pro/bookings/", views.ProBookingListView.as_view(), name="pro-bookings"),
    path(
        "pro/bookings/<uuid:public_id>/",
        views.ProBookingDetailView.as_view(),
        name="pro-booking-detail",
    ),
    path(
        "pro/bookings/<uuid:public_id>/confirm/",
        views.ProBookingConfirmView.as_view(),
        name="pro-booking-confirm",
    ),
    path(
        "pro/bookings/<uuid:public_id>/cancel/",
        views.ProBookingCancelView.as_view(),
        name="pro-booking-cancel",
    ),
]
