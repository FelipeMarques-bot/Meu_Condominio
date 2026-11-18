import logging
import sys
import threading

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

CHAVE_AGENDADOR = "agendador:prazos"
INTERVALO_SEGUNDOS = 6 * 60 * 60


def _em_testes() -> bool:
    return "test" in sys.argv or "pytest" in sys.argv[0]


def _executar_tarefas() -> None:
    from django.db import close_old_connections

    from apps.reservas.prazos import processar_prazos

    try:
        close_old_connections()
        resumo = processar_prazos()
        logger.info("Agendador interno: %s", resumo)
    except Exception:
        logger.exception("Falha no agendador interno de prazos")
    finally:
        close_old_connections()


class AgendadorMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            getattr(settings, "AGENDADOR_INTERNO", False)
            and not _em_testes()
            and request.method == "GET"
            and not request.path.startswith(("/static/", "/media/"))
        ):
            try:
                if cache.add(CHAVE_AGENDADOR, "1", INTERVALO_SEGUNDOS):
                    threading.Thread(target=_executar_tarefas, daemon=True).start()
            except Exception:
                logger.warning("Não foi possível agendar as tarefas de prazos")
        return self.get_response(request)
