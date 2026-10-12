from django.urls import path

from . import views

urlpatterns = [
    path("trades/", views.TradeList.as_view(), name="trade-list"),
    path("trades/<slug:slug>/", views.TradeDetail.as_view(), name="trade-detail"),
    path("zones/", views.ZoneList.as_view(), name="zone-list"),
    path("pros/", views.ProList.as_view(), name="pro-list"),
    path("pros/<int:id>/", views.ProDetail.as_view(), name="pro-detail"),
    path("reviews/", views.ReviewList.as_view(), name="review-list"),
    path("stats/", views.stats, name="stats"),
    path("site/", views.site, name="site"),
]
