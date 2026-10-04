from django.urls import path

from . import views

urlpatterns = [
    path(
        "bookings/<uuid:public_id>/review/",
        views.BookingReviewView.as_view(),
        name="booking-review",
    ),
]
