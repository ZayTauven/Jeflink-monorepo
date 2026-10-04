from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from jeflink.common.api.views import HealthView


class SchemaView(SpectacularAPIView):
    rate_limit_scope = "api_docs"


class DocsView(SpectacularSwaggerView):
    rate_limit_scope = "api_docs"


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", HealthView.as_view(), name="health"),
    path("api/", include("jeflink.accounts.api.urls")),
    path("api/catalog/", include("jeflink.catalog.api.urls")),
    path("api/zones/", include("jeflink.zones.api.urls")),
    path("api/", include("jeflink.providers.api.urls")),
    path("api/", include("jeflink.requests.api.urls")),
    path("api/", include("jeflink.bookings.api.urls")),
    path("api/", include("jeflink.reviews.api.urls")),
]

# Schéma et documentation seulement en local/test ; `make openapi` passe par la commande (S24).
if settings.SERVE_API_SCHEMA:
    urlpatterns += [
        path("api/schema/", SchemaView.as_view(), name="schema"),
        path("api/docs/", DocsView.as_view(url_name="schema"), name="api-docs"),
    ]
