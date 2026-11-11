import json
import logging
import urllib.error
import urllib.request

from django.conf import settings

from .models import ConfiguracaoCondominio

logger = logging.getLogger(__name__)


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
        with urllib.request.urlopen(
            requisicao, timeout=settings.TELEGRAM_TIMEOUT
        ) as resposta:
            return resposta.status == 200
    except (urllib.error.URLError, TimeoutError, ValueError):
        logger.warning("Falha ao enviar mensagem ao Telegram", exc_info=True)
        return False
