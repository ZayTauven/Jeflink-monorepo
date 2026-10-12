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

urlpatterns = [
    path("overview/", views.overview, name="console-overview"),
    path("badges/", views.badges, name="console-badges"),
    *router.urls,
]
