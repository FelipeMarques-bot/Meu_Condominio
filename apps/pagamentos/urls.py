from django.urls import path

from . import views

urlpatterns = [
    path(
        "pix/webhook/abacatepay/<slug:slug>/<str:token>/",
        views.webhook_abacatepay,
        name="webhook_abacatepay",
    ),
]
