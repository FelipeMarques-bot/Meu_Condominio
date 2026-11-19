from django.contrib import admin

from .models import Condominio, ConfiguracaoCondominio, PagamentoPlano, Plano


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
    list_display = (
        "nome",
        "slug",
        "plano",
        "assinatura_valida_ate",
        "isento_assinatura",
        "ativo",
        "criado_em",
    )
    list_filter = ("ativo", "plano", "isento_assinatura")
    search_fields = ("nome", "slug")
    prepopulated_fields = {"slug": ("nome",)}
    readonly_fields = ("trial_ip_hash", "trial_telefone_hash", "trial_email_hash")
    inlines = [ConfiguracaoInline]


@admin.register(PagamentoPlano)
class PagamentoPlanoAdmin(admin.ModelAdmin):
    list_display = ("condominio", "plano", "valor", "status", "criado_em")
    list_filter = ("status", "plano")
    search_fields = ("condominio__nome",)
    readonly_fields = ("criado_em", "analisado_em", "analisado_por")
