from django.db.models import Q
from django.utils import timezone

from apps.core.permissoes import pode_gerir, unidades_do_usuario

from .models import ListaEspera, Reserva


def resultados_nao_vistos(usuario, condominio):
    """Reservas do morador com análise nova que ele ainda não abriu."""
    if not usuario.is_authenticated:
        return Reserva.objects.none()
    return (
        Reserva.objects.filter(
            condominio=condominio,
            solicitante=usuario,
            status__in=[Reserva.Status.CONFIRMADA, Reserva.Status.REJEITADA],
            resultado_visto_em__isnull=True,
        )
        .select_related("local", "unidade")
        .distinct()
        .order_by("-atualizado_em")
    )


def esperas_avisadas_nao_vistas(usuario, condominio):
    """Vagas liberadas na lista de espera que o morador ainda não viu no app."""
    if not usuario.is_authenticated:
        return ListaEspera.objects.none()
    return (
        ListaEspera.objects.filter(
            condominio=condominio,
            solicitante=usuario,
            status=ListaEspera.Status.AVISADO,
            aviso_visto_em__isnull=True,
        )
        .select_related("local", "unidade")
        .distinct()
        .order_by("-avisado_em")
    )


def reservas_para_confirmar_hoje(usuario, condominio):
    """Reservas confirmadas para hoje que ainda não tiveram o uso confirmado."""
    if not usuario.is_authenticated:
        return Reserva.objects.none()
    unidades = unidades_do_usuario(usuario, condominio)
    return (
        Reserva.objects.filter(
            condominio=condominio,
            status=Reserva.Status.CONFIRMADA,
            inicio__date=timezone.localdate(),
            checkin_em__isnull=True,
        )
        .filter(Q(solicitante=usuario) | Q(unidade__in=unidades))
        .select_related("local", "unidade")
        .distinct()
        .order_by("inicio")
    )


def reservas_aguardando_gestao(condominio):
    """Pedidos que esperam comprovante ou análise do síndico."""
    if condominio is None:
        return 0
    return Reserva.objects.filter(
        condominio=condominio,
        status__in=[
            Reserva.Status.AGUARDANDO_COMPROVANTE,
            Reserva.Status.EM_ANALISE,
        ],
    ).count()


def condominios_do_usuario(usuario):
    """Condomínios com vínculo ativo, usados no seletor de troca rápida."""
    if not usuario.is_authenticated:
        return []
    if usuario.is_superuser:
        from apps.core.models import Condominio

        return list(Condominio.objects.filter(ativo=True).order_by("nome"))

    vistos = {}
    vinculos = (
        usuario.vinculos.filter(ativo=True)
        .select_related("unidade__condominio")
        .order_by("unidade__condominio__nome")
    )
    for vinculo in vinculos:
        condominio = vinculo.unidade.condominio
        vistos.setdefault(condominio.pk, condominio)
    return list(vistos.values())


def pode_gerir_algum(usuario, condominios):
    return any(pode_gerir(usuario, condominio) for condominio in condominios)

