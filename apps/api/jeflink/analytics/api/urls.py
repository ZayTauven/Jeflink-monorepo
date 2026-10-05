from django.urls import path

from .views import PublicStatsView

urlpatterns = [path("", PublicStatsView.as_view(), name="stats")]
