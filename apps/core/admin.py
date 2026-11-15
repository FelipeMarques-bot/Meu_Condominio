from django.contrib import admin

from .models import Condominio, ConfiguracaoCondominio, Plano


@admin.register(Plano)
class PlanoAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "preco_mensal",
        "limite_unidades",
        "limite_locais",
        "ordem",
        "ativo",
    )
    list_editable = ("preco_mensal", "ativo")
    ordering = ("ordem",)


class ConfiguracaoInline(admin.StackedInline):
    model = ConfiguracaoCondominio
    extra = 0


@admin.register(Condominio)
class CondominioAdmin(admin.ModelAdmin):
    list_display = ("nome", "slug", "plano", "ativo", "criado_em")
    list_filter = ("ativo", "plano")
    search_fields = ("nome", "slug")
    prepopulated_fields = {"slug": ("nome",)}
    inlines = [ConfiguracaoInline]
