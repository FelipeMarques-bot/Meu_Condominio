import re

from django.shortcuts import redirect

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


class AssinaturaMiddleware:
    """Suspende o acesso ao condomínio quando o teste acabou e não há plano pago."""

    ROTAS_LIVRES = {"assinatura", "minha_conta", "trocar_senha"}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not request.user.is_authenticated or request.user.is_superuser:
            return None
        if not view_kwargs.get("slug"):
            return None
        nome_rota = getattr(request.resolver_match, "url_name", "")
        if nome_rota in self.ROTAS_LIVRES:
            return None

        condominio = getattr(request, "condominio", None)
        if condominio is None or condominio.acesso_liberado:
            return None
        if not request.user.vinculos.filter(
            ativo=True, unidade__condominio=condominio
        ).exists():
            return None

        return redirect("assinatura", slug=condominio.slug)
