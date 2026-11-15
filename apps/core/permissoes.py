from functools import wraps

from django.core.exceptions import PermissionDenied
from django.http import Http404

from apps.usuarios.models import Unidade, VinculoUnidade


def _papeis(usuario, condominio) -> set[str]:
    if not usuario.is_authenticated:
        return set()
    return set(
        usuario.vinculos.filter(
            ativo=True, unidade__condominio=condominio
        ).values_list("papel", flat=True)
    )


def eh_sindico(usuario, condominio) -> bool:
    if not usuario.is_authenticated:
        return False
    return usuario.is_superuser or VinculoUnidade.Papel.SINDICO in _papeis(
        usuario, condominio
    )


def eh_administradora(usuario, condominio) -> bool:
    return bool(
        usuario.is_authenticated
        and VinculoUnidade.Papel.ADMINISTRADORA in _papeis(usuario, condominio)
    )


def existe_administradora(condominio) -> bool:
    return VinculoUnidade.objects.filter(
        ativo=True,
        papel=VinculoUnidade.Papel.ADMINISTRADORA,
        unidade__condominio=condominio,
    ).exists()


def pode_gerir(usuario, condominio) -> bool:
    """Ajustes do condomínio: administradora; síndico só se não houver administradora."""
    if not usuario.is_authenticated:
        return False
    if usuario.is_superuser or eh_administradora(usuario, condominio):
        return True
    return eh_sindico(usuario, condominio) and not existe_administradora(condominio)


def pode_aprovar(usuario, condominio) -> bool:
    """Aprovação final de reservas e comprovantes: síndico."""
    return eh_sindico(usuario, condominio)


def eh_admin_condominio(usuario, condominio) -> bool:
    return eh_sindico(usuario, condominio) or eh_administradora(usuario, condominio)


def unidades_do_usuario(usuario, condominio):
    if not usuario.is_authenticated:
        return Unidade.objects.none()
    return Unidade.objects.filter(
        condominio=condominio,
        vinculos__usuario=usuario,
        vinculos__ativo=True,
    ).distinct()


def pode_ver_reserva(usuario, reserva) -> bool:
    if eh_admin_condominio(usuario, reserva.condominio):
        return True
    if reserva.solicitante_id == usuario.pk:
        return True
    return reserva.unidade.vinculos.filter(usuario=usuario, ativo=True).exists()


def _decorador(verifica, mensagem: str):
    def wrapper(view):
        @wraps(view)
        def _wrapped(request, slug, *args, **kwargs):
            condominio = getattr(request, "condominio", None)
            if condominio is None:
                raise Http404("Condomínio não encontrado.")
            if not verifica(request.user, condominio):
                raise PermissionDenied(mensagem)
            return view(request, slug, *args, **kwargs)

        return _wrapped

    return wrapper


gestao_required = _decorador(
    pode_gerir, "Somente a administração pode ajustar este condomínio."
)
sindico_required = _decorador(
    pode_aprovar, "Somente o síndico pode aprovar reservas e comprovantes."
)
