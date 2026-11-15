from django.contrib.auth import views as auth_views
from django.urls import path

from . import views
from .forms import EntrarForm

urlpatterns = [
    path("", views.landing, name="landing"),
    path("criar/", views.criar_condominio, name="criar_condominio"),
    path(
        "entrar/",
        auth_views.LoginView.as_view(
            template_name="core/login.html",
            authentication_form=EntrarForm,
            redirect_authenticated_user=True,
        ),
        name="login",
    ),
    path("sair/", auth_views.LogoutView.as_view(), name="logout"),
    path("plataforma/entrar/", views.plataforma_entrar, name="plataforma_entrar"),
    path("plataforma/", views.plataforma_painel, name="plataforma"),
    path(
        "plataforma/sair/",
        auth_views.LogoutView.as_view(next_page="plataforma_entrar"),
        name="plataforma_sair",
    ),
    path("c/<slug:slug>/", views.painel_redirect, name="painel_redirect"),
    path("c/<slug:slug>/agenda/", views.agenda, name="agenda"),
    path("c/<slug:slug>/gestao/", views.gestao, name="gestao"),
    path("c/<slug:slug>/configuracoes/", views.configuracoes, name="configuracoes"),
    path("c/<slug:slug>/identidade/", views.identidade, name="identidade"),
    path("c/<slug:slug>/locais/", views.locais, name="locais"),
    path("c/<slug:slug>/locais/<int:pk>/editar/", views.local_editar, name="local_editar"),
    path(
        "c/<slug:slug>/locais/<int:pk>/alternar/",
        views.local_alternar,
        name="local_alternar",
    ),
    path("c/<slug:slug>/unidades/", views.unidades, name="unidades"),
    path(
        "c/<slug:slug>/unidades/<int:pk>/editar/",
        views.unidade_editar,
        name="unidade_editar",
    ),
    path("c/<slug:slug>/convites/", views.convites, name="convites"),
    path("c/<slug:slug>/convite/<uuid:token>/", views.usar_convite, name="usar_convite"),
]
