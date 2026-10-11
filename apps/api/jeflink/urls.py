from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

admin.site.site_header = "Jeflink — administration"
admin.site.site_title = "Jeflink"
admin.site.index_title = "Back-office de démo"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("jeflink.accounts.urls")),
    path("api/", include("jeflink.catalog.urls")),
    path("api/", include("jeflink.jobs.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]
