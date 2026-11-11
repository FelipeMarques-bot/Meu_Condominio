from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Condominio, ConfiguracaoCondominio


@receiver(post_save, sender=Condominio)
def criar_configuracao_padrao(sender, instance, created, **kwargs):
    if created:
        ConfiguracaoCondominio.objects.get_or_create(condominio=instance)
