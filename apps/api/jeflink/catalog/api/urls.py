from django.urls import path

from .views import CoverageView, TradeDetailView, TradeListView

urlpatterns = [
    path("coverage/", CoverageView.as_view(), name="catalog-coverage"),
    path("trades/", TradeListView.as_view(), name="catalog-trades"),
    path("trades/<str:slug>/", TradeDetailView.as_view(), name="catalog-trade"),
]
