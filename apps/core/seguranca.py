import hashlib

from django.conf import settings
from django.core.cache import cache

LIMITE_TENTATIVAS = 5
JANELA_SEGUNDOS = 15 * 60


def _ip(request) -> str:
    if getattr(settings, "CONFIAR_NO_PROXY", False):
        encaminhado = request.META.get("HTTP_X_FORWARDED_FOR", "")
        primeiro = encaminhado.split(",")[0].strip()
        if primeiro:
            return primeiro
    return request.META.get("REMOTE_ADDR", "")


def chave_tentativas(request, username: str) -> str:
    resumo = hashlib.sha256(
        f"{_ip(request)}|{(username or '').strip().lower()}".encode()
    ).hexdigest()[:24]
    return f"login:tentativas:{resumo}"


def bloqueado(chave: str) -> bool:
    return int(cache.get(chave, 0)) >= LIMITE_TENTATIVAS


def registrar_falha(chave: str) -> None:
    cache.set(chave, int(cache.get(chave, 0)) + 1, JANELA_SEGUNDOS)


def limpar(chave: str) -> None:
    cache.delete(chave)
