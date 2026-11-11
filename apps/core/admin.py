from django.contrib import admin

from .models import Condominio, ConfiguracaoCondominio


class ConfiguracaoInline(admin.StackedInline):
    model = ConfiguracaoCondominio
    extra = 0


@admin.register(Condominio)
class CondominioAdmin(admin.ModelAdmin):
    list_display = ("nome", "slug", "ativo", "criado_em")
    list_filter = ("ativo",)
    search_fields = ("nome", "slug")
    prepopulated_fields = {"slug": ("nome",)}
    inlines = [ConfiguracaoInline]
