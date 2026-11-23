from django.db.models import Q

from apps.core.permissoes import unidades_do_usuario

from .models import Reserva


def resultados_nao_vistos(usuario, condominio):
    """Reservas do morador com análise nova que ele ainda não abriu."""
    if not usuario.is_authenticated:
        return Reserva.objects.none()
    unidades = unidades_do_usuario(usuario, condominio)
    return (
        Reserva.objects.filter(
            condominio=condominio,
            status__in=[Reserva.Status.CONFIRMADA, Reserva.Status.REJEITADA],
            resultado_visto_em__isnull=True,
        )
        .filter(Q(solicitante=usuario) | Q(unidade__in=unidades))
        .select_related("local", "unidade")
        .distinct()
        .order_by("-atualizado_em")
    )
