from rest_framework.routers import SimpleRouter

from .views import RequestViewSet

router = SimpleRouter()
router.register("requests", RequestViewSet, basename="request")

urlpatterns = router.urls
