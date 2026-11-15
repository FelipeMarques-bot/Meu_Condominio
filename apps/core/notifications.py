import json
import logging
import urllib.error
import urllib.request

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.utils import timezone

from .models import ConfiguracaoCondominio

logger = logging.getLogger(__name__)


def emails_administradores(condominio) -> list[str]:
    from apps.usuarios.models import VinculoUnidade

    return list(
        get_user_model()
        .objects.filter(
            vinculos__unidade__condominio=condominio,
            vinculos__ativo=True,
            vinculos__papel__in=[
                VinculoUnidade.Papel.SINDICO,
                VinculoUnidade.Papel.ADMINISTRADORA,
            ],
        )
        .exclude(email="")
        .values_list("email", flat=True)
        .distinct()
    )


def _data_hora(reserva) -> str:
    return timezone.localtime(reserva.inicio).strftime("%d/%m/%Y às %H:%M")


def notificar_nova_analise(reserva) -> None:
    assunto = f"Novo comprovante para análise · {reserva.local.nome}"
    corpo = (
        f"{reserva.solicitante or reserva.unidade.rotulo} enviou um comprovante.\n\n"
        f"Espaço: {reserva.local.nome}\n"
        f"Unidade: {reserva.unidade.rotulo}\n"
        f"Data: {_data_hora(reserva)}\n"
        f"Valor: R$ {reserva.valor:.2f}\n\n"
        "Acesse o painel para aprovar ou recusar."
    )
    destinatarios = emails_administradores(reserva.condominio)
    if destinatarios:
        send_mail(assunto, corpo, settings.DEFAULT_FROM_EMAIL, destinatarios, fail_silently=True)

    enviar_telegram(
        reserva.condominio,
        f"{assunto}\n{reserva.unidade.rotulo} · {_data_hora(reserva)}",
    )


def notificar_reserva_confirmada(reserva) -> None:
    if not reserva.solicitante or not reserva.solicitante.email:
        return
    assunto = f"Reserva confirmada · {reserva.local.nome}"
    corpo = (
        f"Sua reserva foi confirmada.\n\n"
        f"Espaço: {reserva.local.nome}\n"
        f"Data: {_data_hora(reserva)}\n"
        f"Código de check-in: {reserva.codigo_checkin}\n\n"
        "Apresente o código no dia do uso."
    )
    send_mail(
        assunto,
        corpo,
        settings.DEFAULT_FROM_EMAIL,
        [reserva.solicitante.email],
        fail_silently=True,
    )


def notificar_reserva_rejeitada(reserva) -> None:
    if not reserva.solicitante or not reserva.solicitante.email:
        return
    assunto = f"Comprovante recusado · {reserva.local.nome}"
    corpo = (
        f"O comprovante da reserva foi recusado.\n\n"
        f"Espaço: {reserva.local.nome}\n"
        f"Data: {_data_hora(reserva)}\n"
        f"Motivo: {reserva.motivo_rejeicao}\n\n"
        "Você pode enviar um novo comprovante pelo painel da reserva."
    )
    send_mail(
        assunto,
        corpo,
        settings.DEFAULT_FROM_EMAIL,
        [reserva.solicitante.email],
        fail_silently=True,
    )


def _configuracao(condominio):
    return ConfiguracaoCondominio.objects.filter(condominio_id=condominio.pk).first()


def telegram_configurado(condominio) -> bool:
    configuracao = _configuracao(condominio)
    return bool(
        configuracao
        and configuracao.telegram_ativo
        and configuracao.telegram_chat_id
        and settings.TELEGRAM_BOT_TOKEN
    )


def enviar_telegram(condominio, texto: str) -> bool:
    configuracao = _configuracao(condominio)
    if not (
        configuracao
        and configuracao.telegram_ativo
        and configuracao.telegram_chat_id
        and settings.TELEGRAM_BOT_TOKEN
    ):
        return False

    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    corpo = json.dumps(
        {
            "chat_id": configuracao.telegram_chat_id,
            "text": texto,
            "disable_web_page_preview": True,
        },
        ensure_ascii=False,
    ).encode("utf-8")

    requisicao = urllib.request.Request(
        url, data=corpo, headers={"Content-Type": "application/json"}
    )

    try:
        # URL fixa da API do Telegram (https), sem entrada do usuário.
        with urllib.request.urlopen(  # nosec B310
            requisicao, timeout=settings.TELEGRAM_TIMEOUT
        ) as resposta:
            return resposta.status == 200
    except (urllib.error.URLError, TimeoutError, ValueError):
        logger.warning("Falha ao enviar mensagem ao Telegram", exc_info=True)
        return False
