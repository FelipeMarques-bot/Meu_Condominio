import re

from .models import Condominio
from .tenancy import reset_current_condominio, set_current_condominio

_PREFIXO_CONDOMINIO = re.compile(r"^/c/(?P<slug>[^/]+)/")


class TenantMiddleware:
    """Resolve o condomínio pelo prefixo /c/<slug>/ e ativa o escopo do TenantManager."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = None
        match = _PREFIXO_CONDOMINIO.match(request.path)
        if match:
            condominio = Condominio.objects.filter(
                slug=match.group("slug"), ativo=True
            ).first()
            if condominio is not None:
                request.condominio = condominio
                token = set_current_condominio(condominio)

        try:
            return self.get_response(request)
        finally:
            if token is not None:
                reset_current_condominio(token)
