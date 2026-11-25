from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Convite, Unidade, Usuario, VinculoUnidade


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Contato", {"fields": ("telefone",)}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("Contato", {"fields": ("telefone",)}),)
    list_display = ("username", "email", "telefone", "is_staff", "is_active")


@admin.register(Unidade)
class UnidadeAdmin(admin.ModelAdmin):
    list_display = ("rotulo", "condominio", "bloco", "numero", "limite_reservas_mes")
    list_filter = ("condominio",)
    search_fields = ("bloco", "numero")


@admin.register(VinculoUnidade)
class VinculoUnidadeAdmin(admin.ModelAdmin):
    list_display = ("usuario", "unidade", "papel", "ativo")
    list_filter = ("papel", "ativo", "unidade__condominio")
    search_fields = ("usuario__username", "usuario__email")


@admin.register(Convite)
class ConviteAdmin(admin.ModelAdmin):
    list_display = ("unidade", "papel", "condominio", "criado_em", "expira_em", "usado_por")
    list_filter = ("papel", "condominio", "usado_em")
    search_fields = ("unidade__numero", "usuario__email")
    readonly_fields = ("token", "criado_em", "usado_em", "usado_por")
