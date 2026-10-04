from django.urls import path

from .views import ProMeView

urlpatterns = [
    path("pro/me/", ProMeView.as_view(), name="pro-me"),
]
