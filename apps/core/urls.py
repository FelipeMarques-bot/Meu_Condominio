from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.landing, name="landing"),
    path("manifest.webmanifest", views.manifest, name="manifest"),
    path("sw.js", views.service_worker, name="service_worker"),
    path("tarefas/prazos/<str:token>/", views.tarefas_prazos, name="tarefas_prazos"),
    path("criar/", views.criar_condominio, name="criar_condominio"),
    path("entrar/", views.EntrarView.as_view(), name="login"),
    path("meus-condominios/", views.meus_condominios, name="meus_condominios"),
    path("sair/", auth_views.LogoutView.as_view(), name="logout"),
    path("plataforma/entrar/", views.plataforma_entrar, name="plataforma_entrar"),
    path("plataforma/", views.plataforma_painel, name="plataforma"),
    path(
        "plataforma/armazenamento/",
        views.plataforma_armazenamento,
        name="plataforma_armazenamento",
    ),
    path(
        "plataforma/pagamentos/<int:pk>/analisar/",
        views.plataforma_pagamento_confirmar,
        name="plataforma_pagamento_confirmar",
    ),
    path(
        "plataforma/pagamentos/<int:pk>/comprovante/",
        views.plataforma_pagamento_comprovante,
        name="plataforma_pagamento_comprovante",
    ),
    path(
        "plataforma/condominios/<int:pk>/liberar/",
        views.plataforma_liberar,
        name="plataforma_liberar",
    ),
    path(
        "plataforma/sair/",
        auth_views.LogoutView.as_view(next_page="plataforma_entrar"),
        name="plataforma_sair",
    ),
    path("c/<slug:slug>/", views.painel_redirect, name="painel_redirect"),
    path("c/<slug:slug>/agenda/", views.agenda, name="agenda"),
    path("c/<slug:slug>/assinatura/", views.assinatura, name="assinatura"),
    path("c/<slug:slug>/conta/", views.minha_conta, name="minha_conta"),
    path(
        "c/<slug:slug>/conta/senha/",
        views.TrocarSenhaView.as_view(),
        name="trocar_senha",
    ),
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
    path(
        "c/<slug:slug>/convites/<int:pk>/excluir/",
        views.convite_excluir,
        name="convite_excluir",
    ),
    path(
        "c/<slug:slug>/vinculos/<int:pk>/remover/",
        views.vinculo_remover,
        name="vinculo_remover",
    ),
    path(
        "c/<slug:slug>/vinculos/<int:pk>/senha/",
        views.vinculo_redefinir_senha,
        name="vinculo_redefinir_senha",
    ),
    path("c/<slug:slug>/convite/<uuid:token>/", views.usar_convite, name="usar_convite"),
]
