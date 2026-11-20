import json
import logging
import urllib.error
import urllib.request
from email.utils import parseaddr

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)

_API_URLS = {
    "brevo": "https://api.brevo.com/v3/smtp/email",
    "resend": "https://api.resend.com/emails",
}


def api_configurada() -> bool:
    return bool(
        settings.EMAIL_API_KEY
        and settings.EMAIL_API_PROVIDER in _API_URLS
    )


def email_configurado() -> bool:
    return api_configurada() or bool(settings.EMAIL_HOST)


def _destinatarios(destinatarios) -> list[str]:
    return [
        email
        for email in dict.fromkeys(destinatarios or [])
        if email and "@" in email
    ]


def _payload(assunto: str, corpo: str, contatos: list[str]) -> tuple[str, dict, dict]:
    provedor = settings.EMAIL_API_PROVIDER
    remetente = settings.DEFAULT_FROM_EMAIL
    if provedor == "brevo":
        nome, email = parseaddr(remetente)
        return (
            _API_URLS[provedor],
            {
                "api-key": settings.EMAIL_API_KEY,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            {
                "sender": {"email": email or remetente, "name": nome},
                "to": [{"email": contato} for contato in contatos],
                "subject": assunto,
                "textContent": corpo,
            },
        )
    return (
        _API_URLS[provedor],
        {
            "Authorization": f"Bearer {settings.EMAIL_API_KEY}",
            "Content-Type": "application/json",
        },
        {
            "from": remetente,
            "to": contatos,
            "subject": assunto,
            "text": corpo,
        },
    )


def _enviar_api(assunto: str, corpo: str, contatos: list[str]) -> bool:
    url, cabecalhos, dados = _payload(assunto, corpo, contatos)
    requisicao = urllib.request.Request(
        url,
        data=json.dumps(dados).encode("utf-8"),
        headers=cabecalhos,
        method="POST",
    )
    try:
        with urllib.request.urlopen(requisicao, timeout=15) as resposta:
            return 200 <= resposta.status < 300
    except urllib.error.HTTPError as erro:
        detalhe = erro.read().decode("utf-8", errors="replace")[:500]
        logger.error(
            "API de e-mail recusou '%s' (%s): %s",
            assunto,
            erro.code,
            detalhe,
        )
    except Exception:
        logger.exception("Falha ao enviar e-mail pela API: %s", assunto)
    return False


def enviar_email(assunto: str, corpo: str, destinatarios) -> bool:
    contatos = _destinatarios(destinatarios)
    if not contatos:
        return False
    if api_configurada():
        return _enviar_api(assunto, corpo, contatos)
    try:
        send_mail(
            assunto,
            corpo,
            settings.DEFAULT_FROM_EMAIL,
            contatos,
            fail_silently=False,
        )
        return True
    except Exception:
        logger.exception("Falha ao enviar e-mail: %s", assunto)
        return False
