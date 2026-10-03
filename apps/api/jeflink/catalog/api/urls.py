from django.urls import path

from .views import TradeDetailView, TradeListView

urlpatterns = [
    path("trades/", TradeListView.as_view(), name="catalog-trades"),
    path("trades/<str:slug>/", TradeDetailView.as_view(), name="catalog-trade"),
]
