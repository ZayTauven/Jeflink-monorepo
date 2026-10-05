from django.urls import path

from .views import ZoneDetailView, ZoneListView, ZoneTradesView

urlpatterns = [
    path("", ZoneListView.as_view(), name="zones"),
    path("<str:slug>/", ZoneDetailView.as_view(), name="zone"),
    path("<str:slug>/trades/", ZoneTradesView.as_view(), name="zone-trades"),
]
