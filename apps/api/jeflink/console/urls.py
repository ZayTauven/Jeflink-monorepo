from django.urls import path

from . import views

urlpatterns = [
    path("overview/", views.overview, name="console-overview"),
    path("badges/", views.badges, name="console-badges"),
]
