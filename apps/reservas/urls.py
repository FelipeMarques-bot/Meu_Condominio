from django.urls import path

from . import views

urlpatterns = [
    path("c/<slug:slug>/reservar/<slug:local_slug>/", views.reservar, name="reservar"),
    path("c/<slug:slug>/reservas/", views.minhas_reservas, name="minhas_reservas"),
    path("c/<slug:slug>/reservas/<int:pk>/", views.reserva_detalhe, name="reserva_detalhe"),
    path("c/<slug:slug>/reservas/<int:pk>/pagamento/", views.pagamento, name="pagamento"),
    path(
        "c/<slug:slug>/reservas/<int:pk>/comprovante/",
        views.enviar_comprovante,
        name="enviar_comprovante",
    ),
    path(
        "c/<slug:slug>/reservas/<int:pk>/comprovante/arquivo/",
        views.baixar_comprovante,
        name="baixar_comprovante",
    ),
    path(
        "c/<slug:slug>/reservas/<int:pk>/cancelar/",
        views.cancelar_reserva,
        name="cancelar_reserva",
    ),
    path("c/<slug:slug>/painel/", views.painel, name="painel"),
    path(
        "c/<slug:slug>/painel/reservas/<int:pk>/",
        views.analise_reserva,
        name="analise_reserva",
    ),
    path(
        "c/<slug:slug>/painel/reservas/<int:pk>/confirmar/",
        views.confirmar_reserva,
        name="confirmar_reserva",
    ),
    path(
        "c/<slug:slug>/painel/reservas/<int:pk>/rejeitar/",
        views.rejeitar_reserva,
        name="rejeitar_reserva",
    ),
]
