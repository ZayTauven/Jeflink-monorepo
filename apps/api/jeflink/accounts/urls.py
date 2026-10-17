from django.urls import path

from . import views

urlpatterns = [
    path("register/", views.register, name="register"),
    path("login/", views.login, name="login"),
    path("logout/", views.logout, name="logout"),
    path("me/", views.me, name="me"),
    path("me/photo/", views.my_photo, name="my-photo"),
    path("me/addresses/", views.my_addresses, name="my-addresses"),
    path("me/addresses/<int:pk>/", views.my_address, name="my-address"),
    path("contact/", views.contact, name="contact"),
]
