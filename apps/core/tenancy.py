from contextvars import ContextVar

from django.db import models

_condominio_atual: ContextVar = ContextVar("condominio_atual", default=None)


def set_current_condominio(condominio):
    return _condominio_atual.set(condominio)


def get_current_condominio():
    return _condominio_atual.get()


def reset_current_condominio(token) -> None:
    _condominio_atual.reset(token)


class TenantManager(models.Manager):
    """Filtra automaticamente pelo condomínio resolvido na requisição.

    Sem condomínio no contexto (admin da plataforma, comandos, testes),
    o queryset completo é retornado.
    """

    def get_queryset(self):
        queryset = super().get_queryset()
        condominio = get_current_condominio()
        if condominio is not None:
            queryset = queryset.filter(condominio=condominio)
        return queryset
