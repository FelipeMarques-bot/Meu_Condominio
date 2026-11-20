import json
import logging
import urllib.error
import urllib.request

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from .email import enviar_email
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


def _moeda(reserva) -> str:
    return f"R$ {reserva.valor:.2f}".replace(".", ",")


def _enviar_email(assunto: str, corpo: str, destinatarios) -> bool:
    return enviar_email(assunto, corpo, destinatarios)


def _configuracao(condominio):
    return ConfiguracaoCondominio.objects.filter(condominio_id=condominio.pk).first()


def _prazo_analise(condominio) -> str:
    configuracao = _configuracao(condominio)
    return str(configuracao.prazo_analise_horas) if configuracao else "24"


def notificar_reserva_criada(reserva) -> None:
    limite = "2 horas"
    if reserva.expira_em:
        limite = timezone.localtime(reserva.expira_em).strftime("%d/%m/%Y às %H:%M")

    if reserva.solicitante and reserva.solicitante.email:
        _enviar_email(
            f"Reserva pré-reservada · {reserva.local.nome}",
            (
                "Recebemos o seu pedido de reserva.\n\n"
                f"Espaço: {reserva.local.nome}\n"
                f"Unidade: {reserva.unidade.rotulo}\n"
                f"Data: {_data_hora(reserva)}\n"
                f"Valor: {_moeda(reserva)}\n\n"
                f"Envie o comprovante até {limite} para não perder o horário."
            ),
            [reserva.solicitante.email],
        )

    assunto = f"Nova reserva aguardando comprovante · {reserva.local.nome}"
    _enviar_email(
        assunto,
        (
            f"{reserva.solicitante or reserva.unidade.rotulo} iniciou uma reserva.\n\n"
            f"Espaço: {reserva.local.nome}\n"
            f"Unidade: {reserva.unidade.rotulo}\n"
            f"Data: {_data_hora(reserva)}\n"
            f"Valor: {_moeda(reserva)}\n\n"
            f"O morador tem até {limite} para enviar o comprovante."
        ),
        emails_administradores(reserva.condominio),
    )
    enviar_telegram(
        reserva.condominio,
        "\n".join(
            [
                assunto,
                f"{reserva.unidade.rotulo} · {_data_hora(reserva)}",
                f"Comprovante até {limite}.",
            ]
        ),
    )


def notificar_nova_analise(reserva) -> None:
    assunto = f"Novo comprovante para análise · {reserva.local.nome}"
    corpo = (
        f"{reserva.solicitante or reserva.unidade.rotulo} enviou um comprovante.\n\n"
        f"Espaço: {reserva.local.nome}\n"
        f"Unidade: {reserva.unidade.rotulo}\n"
        f"Data: {_data_hora(reserva)}\n"
        f"Valor: {_moeda(reserva)}\n\n"
        f"Você tem até {_prazo_analise(reserva.condominio)} horas para analisar. "
        "Acesse o painel para aprovar ou recusar."
    )
    _enviar_email(assunto, corpo, emails_administradores(reserva.condominio))
    enviar_telegram(
        reserva.condominio,
        f"{assunto}\n{reserva.unidade.rotulo} · {_data_hora(reserva)}",
    )


def notificar_reserva_confirmada(reserva) -> None:
    if not reserva.solicitante or not reserva.solicitante.email:
        return
    _enviar_email(
        f"Reserva confirmada · {reserva.local.nome}",
        (
            "Sua reserva foi confirmada.\n\n"
            f"Espaço: {reserva.local.nome}\n"
            f"Data: {_data_hora(reserva)}\n"
            f"Código de check-in: {reserva.codigo_checkin}\n\n"
            "Apresente o código no dia do uso."
        ),
        [reserva.solicitante.email],
    )


def notificar_reserva_rejeitada(reserva) -> None:
    if not reserva.solicitante or not reserva.solicitante.email:
        return
    _enviar_email(
        f"Comprovante recusado · {reserva.local.nome}",
        (
            "O comprovante da reserva foi recusado.\n\n"
            f"Espaço: {reserva.local.nome}\n"
            f"Data: {_data_hora(reserva)}\n"
            f"Motivo: {reserva.motivo_rejeicao}\n\n"
            "Você pode enviar um novo comprovante pelo painel da reserva."
        ),
        [reserva.solicitante.email],
    )


def notificar_reserva_cancelada(reserva) -> None:
    assunto = f"Reserva cancelada · {reserva.local.nome}"
    _enviar_email(
        assunto,
        (
            "Uma reserva foi cancelada e o horário está livre.\n\n"
            f"Espaço: {reserva.local.nome}\n"
            f"Unidade: {reserva.unidade.rotulo}\n"
            f"Data: {_data_hora(reserva)}"
        ),
        emails_administradores(reserva.condominio),
    )
    enviar_telegram(
        reserva.condominio,
        f"{assunto}\n{reserva.unidade.rotulo} · {_data_hora(reserva)}",
    )


def notificar_reserva_expirada(reserva, motivo: str = "") -> None:
    detalhe = f"\nMotivo: {motivo}" if motivo else ""
    if reserva.solicitante and reserva.solicitante.email:
        _enviar_email(
            f"Reserva expirada · {reserva.local.nome}",
            (
                "O prazo da sua reserva terminou e o horário foi liberado.\n\n"
                f"Espaço: {reserva.local.nome}\n"
                f"Data: {_data_hora(reserva)}{detalhe}\n\n"
                "Você pode fazer uma nova reserva pelo app."
            ),
            [reserva.solicitante.email],
        )

    assunto = f"Reserva expirada · {reserva.local.nome}"
    _enviar_email(
        assunto,
        (
            "Uma reserva expirou e o horário foi liberado.\n\n"
            f"Espaço: {reserva.local.nome}\n"
            f"Unidade: {reserva.unidade.rotulo}\n"
            f"Data: {_data_hora(reserva)}{detalhe}"
        ),
        emails_administradores(reserva.condominio),
    )
    enviar_telegram(
        reserva.condominio,
        f"{assunto}\n{reserva.unidade.rotulo} · {_data_hora(reserva)}",
    )


def notificar_prazo_vencido(reserva) -> None:
    assunto = f"Prazo de análise vencido · {reserva.local.nome}"
    _enviar_email(
        assunto,
        (
            "O prazo para analisar um comprovante terminou.\n\n"
            f"Espaço: {reserva.local.nome}\n"
            f"Unidade: {reserva.unidade.rotulo}\n"
            f"Data: {_data_hora(reserva)}\n"
            f"Valor: {_moeda(reserva)}\n\n"
            "A reserva continua pendente no painel até você decidir."
        ),
        emails_administradores(reserva.condominio),
    )
    enviar_telegram(
        reserva.condominio,
        f"{assunto}\n{reserva.unidade.rotulo} · {_data_hora(reserva)}",
    )


def notificar_lembrete_reserva(reserva) -> None:
    if not reserva.solicitante or not reserva.solicitante.email:
        return
    _enviar_email(
        f"Lembrete de reserva · {reserva.local.nome}",
        (
            "Sua reserva é amanhã.\n\n"
            f"Espaço: {reserva.local.nome}\n"
            f"Data: {_data_hora(reserva)}\n"
            f"Código de check-in: {reserva.codigo_checkin}\n\n"
            "Leve o código para apresentar no local."
        ),
        [reserva.solicitante.email],
    )


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


def _emails_plataforma() -> list[str]:
    contatos = [settings.CONTATO_EMAIL]
    contatos += list(
        get_user_model()
        .objects.filter(is_superuser=True)
        .exclude(email="")
        .values_list("email", flat=True)
    )
    return [email for email in dict.fromkeys(contatos) if email]


def notificar_pagamento_enviado(pagamento, url_plataforma: str = "") -> None:
    condominio = pagamento.condominio
    dia = pagamento.dia_vencimento or condominio.dia_vencimento or "a definir"
    valor = f"R$ {pagamento.valor:.2f}".replace(".", ",")
    corpo = (
        f"{condominio.nome} enviou um comprovante de pagamento.\n\n"
        f"Plano: {pagamento.plano.nome if pagamento.plano else 'a definir'}\n"
        f"Valor: {valor}\n"
        f"Dia de vencimento escolhido: {dia}\n\n"
    )
    if url_plataforma:
        corpo += f"Confira e libere em: {url_plataforma}\n"
    _enviar_email(
        f"Novo comprovante - {condominio.nome}",
        corpo,
        _emails_plataforma(),
    )


def notificar_pagamento_analisado(
    pagamento, aprovado: bool, vencimento=None
) -> None:
    condominio = pagamento.condominio
    if not emails_administradores(condominio):
        return
    if aprovado:
        assunto = f"Pagamento aprovado - {condominio.nome}"
        corpo = (
            "Seu pagamento foi conferido e o plano está liberado.\n\n"
            f"Condomínio: {condominio.nome}\n"
        )
        if vencimento:
            corpo += f"Próximo vencimento: {vencimento:%d/%m/%Y}\n"
    else:
        assunto = f"Comprovante recusado - {condominio.nome}"
        corpo = (
            "O comprovante enviado não foi aceito.\n\n"
            f"Condomínio: {condominio.nome}\n"
        )
        if pagamento.observacao:
            corpo += f"Motivo: {pagamento.observacao}\n"
        corpo += "\nEnvie um novo comprovante pela tela do plano.\n"
    _enviar_email(assunto, corpo, emails_administradores(condominio))


def link_whatsapp(telefone: str, texto: str) -> str:
    from urllib.parse import quote

    digitos = "".join(caractere for caractere in (telefone or "") if caractere.isdigit())
    if len(digitos) in (10, 11):
        digitos = f"55{digitos}"
    if not digitos:
        return ""
    return f"https://wa.me/{digitos}?text={quote(texto)}"


def notificar_vaga_liberada(entrada) -> None:
    if not entrada.solicitante or not entrada.solicitante.email:
        return
    _enviar_email(
        f"Vaga liberada \u00b7 {entrada.local.nome}",
        (
            "Um hor\u00e1rio que voc\u00ea esperava foi liberado.\n\n"
            f"Espa\u00e7o: {entrada.local.nome}\n"
            f"Data: {entrada.data:%d/%m/%Y}\n\n"
            "Entre no app e fa\u00e7a a reserva antes que outra pessoa pegue."
        ),
        [entrada.solicitante.email],
    )
