from django.contrib import admin

from .models import Local, Reserva


@admin.register(Local)
class LocalAdmin(admin.ModelAdmin):
    list_display = ("nome", "condominio", "categoria", "valor", "capacidade", "ativo")
    list_filter = ("condominio", "categoria", "ativo")
    search_fields = ("nome", "slug")
    prepopulated_fields = {"slug": ("nome",)}


@admin.register(Reserva)
class ReservaAdmin(admin.ModelAdmin):
    list_display = ("local", "unidade", "inicio", "fim", "status", "valor")
    list_filter = ("status", "condominio", "local")
    search_fields = ("local__nome", "unidade__numero", "solicitante__username")
    date_hierarchy = "inicio"
    readonly_fields = ("criado_em", "atualizado_em")
