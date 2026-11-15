from django.conf import settings

from .permissoes import (
    eh_admin_condominio,
    eh_administradora,
    eh_sindico,
    pode_aprovar,
    pode_gerir,
)


def marca(request):
    condominio = getattr(request, "condominio", None)
    usuario = request.user
    return {
        "site_nome": settings.SITE_NOME,
        "contato_email": settings.CONTATO_EMAIL,
        "condominio_atual": condominio,
        "sou_admin": bool(
            condominio and eh_admin_condominio(usuario, condominio)
        ),
        "sou_sindico": bool(condominio and eh_sindico(usuario, condominio)),
        "sou_administradora": bool(
            condominio and eh_administradora(usuario, condominio)
        ),
        "pode_gerir": bool(condominio and pode_gerir(usuario, condominio)),
        "pode_aprovar": bool(condominio and pode_aprovar(usuario, condominio)),
    }
