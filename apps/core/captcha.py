import json
import logging
import urllib.parse
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)


def captcha_configurado() -> bool:
    return bool(
        getattr(settings, "TURNSTILE_SITE_KEY", "")
        and getattr(settings, "TURNSTILE_SECRET_KEY", "")
    )


def verificar_captcha(request) -> tuple[bool, str]:
    if not captcha_configurado():
        return True, ""
    token = (request.POST.get("cf-turnstile-response") or "").strip()
    if not token:
        return False, "Confirme que você não é um robô antes de continuar."
    dados = urllib.parse.urlencode(
        {
            "secret": settings.TURNSTILE_SECRET_KEY,
            "response": token,
            "remoteip": request.META.get("REMOTE_ADDR", ""),
        }
    ).encode()
    requisicao = urllib.request.Request(
        "https://challenges.cloudflare.com/turnstile/v0/siteverify",
        data=dados,
        method="POST",
    )
    try:
        with urllib.request.urlopen(requisicao, timeout=6) as resposta:
            resultado = json.loads(resposta.read().decode("utf-8"))
    except Exception:
        logger.exception("Falha ao validar o Turnstile")
        return False, "Não foi possível validar o Captcha. Tente novamente."
    if resultado.get("success"):
        return True, ""
    return False, "Captcha inválido ou expirado. Tente novamente."
