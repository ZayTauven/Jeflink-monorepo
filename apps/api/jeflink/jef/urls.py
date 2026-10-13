from django.urls import path

from . import views

urlpatterns = [
    path("jef/", views.start, name="jef-start"),
    path("jef/<int:pk>/brief/", views.brief, name="jef-brief"),
]
