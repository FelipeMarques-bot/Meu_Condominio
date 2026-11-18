from datetime import datetime, time, timedelta

from django.utils import timezone

from apps.core.models import ConfiguracaoCondominio
from apps.core.notifications import (
    notificar_lembrete_reserva,
    notificar_prazo_vencido,
    notificar_reserva_expirada,
)

from .models import Reserva


def _base():
    return Reserva.all_objects.select_related(
        "local", "unidade", "solicitante", "condominio"
    )


def expirar_sem_comprovante(agora=None) -> int:
    agora = agora or timezone.now()
    total = 0
    reservas = _base().filter(
        status=Reserva.Status.AGUARDANDO_COMPROVANTE,
        expira_em__lt=agora,
    )
    for reserva in reservas:
        reserva.status = Reserva.Status.EXPIRADA
        reserva.save(update_fields=["status", "atualizado_em"])
        notificar_reserva_expirada(reserva, "prazo para envio do comprovante")
        total += 1
    return total


def alertar_prazos(agora=None) -> int:
    agora = agora or timezone.now()
    total = 0
    reservas = _base().filter(
        status=Reserva.Status.EM_ANALISE,
        prazo_analise_em__lt=agora,
        prazo_alertado=False,
    )
    politicas = dict(
        ConfiguracaoCondominio.objects.values_list(
            "condominio_id", "politica_prazo_analise"
        )
    )
    for reserva in reservas:
        politica = politicas.get(
            reserva.condominio_id,
            ConfiguracaoCondominio.PoliticaPrazo.MANTER,
        )
        reserva.prazo_alertado = True
        if politica == ConfiguracaoCondominio.PoliticaPrazo.CANCELAR:
            reserva.status = Reserva.Status.EXPIRADA
            reserva.save(
                update_fields=["status", "prazo_alertado", "atualizado_em"]
            )
            notificar_reserva_expirada(reserva, "prazo de análise vencido")
        else:
            reserva.save(update_fields=["prazo_alertado", "atualizado_em"])
            notificar_prazo_vencido(reserva)
        total += 1
    return total


def enviar_lembretes(dias: int = 1, agora=None) -> int:
    if dias < 0:
        return 0
    agora = agora or timezone.now()
    dia = timezone.localtime(agora + timedelta(days=dias)).date()
    inicio = timezone.make_aware(datetime.combine(dia, time.min))
    fim = inicio + timedelta(days=1)

    total = 0
    reservas = _base().filter(
        status=Reserva.Status.CONFIRMADA,
        inicio__gte=inicio,
        inicio__lt=fim,
        lembrete_enviado=False,
    )
    for reserva in reservas:
        reserva.lembrete_enviado = True
        reserva.save(update_fields=["lembrete_enviado", "atualizado_em"])
        notificar_lembrete_reserva(reserva)
        total += 1
    return total


def processar_prazos(dias_lembrete: int = 1) -> dict:
    agora = timezone.now()
    return {
        "expiradas": expirar_sem_comprovante(agora),
        "prazos_vencidos": alertar_prazos(agora),
        "lembretes": enviar_lembretes(dias_lembrete, agora),
    }
