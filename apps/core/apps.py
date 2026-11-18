from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "Núcleo"

    def ready(self) -> None:
        from django.contrib import admin

        from . import signals  # noqa: F401

        admin.site.site_header = "Meu Condomínio"
        admin.site.site_title = "Meu Condomínio"
        admin.site.index_title = "Administração da plataforma"
