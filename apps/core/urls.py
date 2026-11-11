from django.urls import path

from . import views

urlpatterns = [
    path("", views.landing, name="landing"),
    path("c/<slug:slug>/", views.painel_redirect, name="painel_redirect"),
    path("c/<slug:slug>/agenda/", views.agenda, name="agenda"),
]
