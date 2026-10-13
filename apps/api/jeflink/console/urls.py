from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("requests", views.RequestConsoleViewSet, basename="console-request")
router.register("disputes", views.DisputeConsoleViewSet, basename="console-dispute")
router.register("pros", views.ProConsoleViewSet, basename="console-pro")
router.register("clients", views.ClientConsoleViewSet, basename="console-client")
router.register("reviews", views.ReviewConsoleViewSet, basename="console-review")
router.register("messages", views.ContactConsoleViewSet, basename="console-message")
router.register("audit", views.AuditConsoleViewSet, basename="console-audit")
router.register("trades", views.TradeConsoleViewSet, basename="console-trade")
router.register("zones", views.ZoneConsoleViewSet, basename="console-zone")
router.register("team", views.TeamConsoleViewSet, basename="console-team")
router.register("coupons", views.CouponConsoleViewSet, basename="console-coupon")
router.register("campaigns", views.CampaignConsoleViewSet, basename="console-campaign")
router.register("transactions", views.TransactionConsoleViewSet, basename="console-transaction")
router.register("balances", views.BalanceConsoleViewSet, basename="console-balance")
router.register("jef", views.JefConsoleViewSet, basename="console-jef")

urlpatterns = [
    path("overview/", views.overview, name="console-overview"),
    path("badges/", views.badges, name="console-badges"),
    path("settings/", views.platform_settings, name="console-settings"),
    path("commissions/", views.commissions, name="console-commissions"),
    path("reports/", views.reports, name="console-reports"),
    path("reports/export/", views.reports_export, name="console-reports-export"),
    *router.urls,
]
