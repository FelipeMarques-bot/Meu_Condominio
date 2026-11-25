from urllib.parse import quote

from django.conf import settings
from django.urls import reverse

from .permissoes import (
    eh_admin_condominio,
    eh_administradora,
    eh_sindico,
    pode_aprovar,
    pode_gerir,
)


def _papel_no_condominio(usuario, condominio) -> str:
    if not condominio:
        return ""
    if eh_sindico(usuario, condominio):
        return "Síndico"
    if eh_administradora(usuario, condominio):
        return "Administradora"
    if usuario.is_authenticated:
        return "Morador"
    return "Visitante"


def _montar_link_whatsapp(mensagem_configurada: str, mensagem_padrao: str) -> str:
    link = (settings.PLANO_WHATSAPP or "").strip()
    if not link:
        return ""
    mensagem = (mensagem_configurada or "").strip() or mensagem_padrao
    if "text=" in link:
        if link.rstrip().endswith("text="):
            return f"{link}{quote(mensagem)}"
        return link
    if link.startswith("http"):
        separador = "&" if "?" in link else "?"
        return f"{link}{separador}text={quote(mensagem)}"
    digitos = "".join(caractere for caractere in link if caractere.isdigit())
    if len(digitos) in (10, 11):
        digitos = f"55{digitos}"
    if not digitos:
        return ""
    return f"https://wa.me/{digitos}?text={quote(mensagem)}"


def _link_suporte_whatsapp() -> str:
    return _montar_link_whatsapp(
        settings.PLANO_WHATSAPP_MENSAGEM,
        settings.PLANO_WHATSAPP_MENSAGEM_PADRAO,
    )


def _link_suporte_landing() -> str:
    return _montar_link_whatsapp(
        settings.PLANO_WHATSAPP_MENSAGEM_LANDING,
        settings.PLANO_WHATSAPP_MENSAGEM_LANDING_PADRAO,
    )


def _voltar_url(request) -> str:
    rota = getattr(getattr(request, "resolver_match", None), "url_name", "")
    if not rota:
        return ""
    if not request.user.is_authenticated:
        return reverse("landing")
    if rota in {
        "landing",
        "login",
        "criar_condominio",
        "confirmar_email",
        "confirmar_email_pendente",
        "reenviar_confirmacao_email",
        "plataforma_entrar",
        "meus_condominios",
        "plataforma",
    }:
        return reverse("landing")
    if rota == "plataforma_armazenamento":
        return reverse("plataforma")
    if rota == "senha_temporaria":
        return reverse("meus_condominios")

    condominio = getattr(request, "condominio", None)
    if condominio is None:
        return reverse("meus_condominios")

    slug = condominio.slug
    if rota == "agenda":
        return reverse("meus_condominios")
    if rota == "gestao":
        return reverse("agenda", kwargs={"slug": slug})
    if rota == "painel":
        return reverse("gestao", kwargs={"slug": slug})
    if rota == "analise":
        return reverse("painel", kwargs={"slug": slug})
    if rota == "trocar_senha":
        return reverse("minha_conta", kwargs={"slug": slug})
    if rota == "local_editar":
        return reverse("locais", kwargs={"slug": slug})
    if rota == "unidade_editar":
        return reverse("unidades", kwargs={"slug": slug})
    if rota in {
        "locais",
        "unidades",
        "convites",
        "configuracoes",
        "identidade",
        "relatorios",
        "checkin",
    }:
        return reverse("gestao", kwargs={"slug": slug})
    return reverse("agenda", kwargs={"slug": slug})


def marca(request):
    condominio = getattr(request, "condominio", None)
    usuario = request.user

    pendentes_gestao = 0
    para_confirmar_hoje = []
    condominios = []

    if usuario.is_authenticated:
        from apps.reservas.resultados import (
            condominios_do_usuario,
            reservas_aguardando_gestao,
            reservas_para_confirmar_hoje,
        )

        condominios = condominios_do_usuario(usuario)
        if condominio is not None:
            if pode_aprovar(usuario, condominio):
                pendentes_gestao = reservas_aguardando_gestao(condominio)
            para_confirmar_hoje = list(
                reservas_para_confirmar_hoje(usuario, condominio)
            )

    return {
        "voltar_url_padrao": _voltar_url(request),
        "site_nome": settings.SITE_NOME,
        "contato_email": settings.CONTATO_EMAIL,
        "plano_pix_chave": settings.PLANO_PIX_CHAVE,
        "plano_whatsapp": _link_suporte_whatsapp(),
        "plano_whatsapp_landing": _link_suporte_landing(),
        "captcha_site_key": settings.TURNSTILE_SITE_KEY,
        "condominio_atual": condominio,
        "papel_no_condominio": _papel_no_condominio(usuario, condominio),
        "sou_admin": bool(
            condominio and eh_admin_condominio(usuario, condominio)
        ),
        "sou_sindico": bool(condominio and eh_sindico(usuario, condominio)),
        "sou_administradora": bool(
            condominio and eh_administradora(usuario, condominio)
        ),
        "pode_gerir": bool(condominio and pode_gerir(usuario, condominio)),
        "pode_aprovar": bool(condominio and pode_aprovar(usuario, condominio)),
        "reservas_pendentes_gestao": pendentes_gestao,
        "reservas_para_confirmar_hoje": para_confirmar_hoje,
        "condominios_do_usuario": condominios,
        "tem_varios_condominios": len(condominios) > 1,
    }
