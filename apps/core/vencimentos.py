from django.utils import timezone

from .models import Condominio
from .notifications import notificar_vencimento_plano

DIAS_DE_AVISO = (5, 0, -5)


def enviar_avisos_vencimento(hoje=None) -> int:
    hoje = hoje or timezone.localdate()
    condominios = (
        Condominio.objects.filter(
            ativo=True,
            isento_assinatura=False,
            vencimento_em__isnull=False,
        )
        .exclude(ultimo_aviso_vencimento=hoje)
        .select_related("plano")
    )
    total = 0
    for condominio in condominios.iterator():
        dias = (condominio.vencimento_em - hoje).days
        if dias not in DIAS_DE_AVISO:
            continue
        if not notificar_vencimento_plano(condominio, dias):
            continue
        condominio.ultimo_aviso_vencimento = hoje
        condominio.save(update_fields=["ultimo_aviso_vencimento"])
        total += 1
    return total
