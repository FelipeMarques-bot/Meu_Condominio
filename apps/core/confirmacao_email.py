import logging
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone

logger = logging.getLogger(__name__)

_SALT = "confirmacao-email"
_VALIDADE = timedelta(days=3)


def gerar_token(usuario) -> str:
    return signing.TimestampSigner(salt=_SALT).sign(str(usuario.pk))


def usuario_do_token(token: str):
    from apps.usuarios.models import Usuario

    try:
        pk = signing.TimestampSigner(salt=_SALT).unsign(
            token, max_age=int(_VALIDADE.total_seconds())
        )
    except signing.SignatureExpired:
        return None, "Este link expirou. Peça um novo e-mail de confirmação."
    except signing.BadSignature:
        return None, "Link de confirmação inválido."
    usuario = Usuario.objects.filter(pk=pk).first()
    if usuario is None:
        return None, "Conta não encontrada."
    return usuario, ""


def enviar_confirmacao(request, usuario) -> bool:
    if not usuario.email:
        return False
    link = request.build_absolute_uri(
        reverse("confirmar_email", args=[gerar_token(usuario)])
    )
    corpo = (
        f"Olá, {usuario.first_name or usuario.username}!\n\n"
        "Confirme seu e-mail para ativar o teste gratuito do Meu Condomínio:\n"
        f"{link}\n\n"
        "O link vale por 3 dias. Se você não criou esta conta, ignore esta mensagem.\n"
    )
    try:
        send_mail(
            "Confirme seu e-mail - Meu Condomínio",
            corpo,
            settings.DEFAULT_FROM_EMAIL,
            [usuario.email],
            fail_silently=False,
        )
    except Exception:
        logger.exception("Falha ao enviar confirmação de e-mail para %s", usuario.pk)
        return False
    return True


def iniciar_trials_pendentes(usuario) -> int:
    from apps.core.models import Condominio
    from apps.core.trial import iniciar_trial

    condominios = Condominio.objects.filter(
        unidades__vinculos__usuario=usuario,
        unidades__vinculos__ativo=True,
        trial_ate__isnull=True,
        assinatura_valida_ate__isnull=True,
        isento_assinatura=False,
    ).distinct()
    total = 0
    for condominio in condominios:
        iniciar_trial(condominio)
        total += 1
    return total


def confirmar(usuario) -> None:
    if usuario.email_confirmado_em:
        return
    usuario.email_confirmado_em = timezone.now()
    usuario.save(update_fields=["email_confirmado_em"])
    iniciar_trials_pendentes(usuario)
