from django.conf import settings


def marca(request):
    return {
        "site_nome": settings.SITE_NOME,
        "contato_email": settings.CONTATO_EMAIL,
        "condominio_atual": getattr(request, "condominio", None),
    }
