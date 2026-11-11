from django.shortcuts import get_object_or_404, redirect, render

from apps.reservas.models import Local

from .models import Condominio


def landing(request):
    return render(request, "core/landing.html")


def painel_redirect(request, slug):
    return redirect("agenda", slug=slug)


def agenda(request, slug):
    condominio = getattr(request, "condominio", None)
    if condominio is None:
        condominio = get_object_or_404(Condominio, slug=slug, ativo=True)

    locais = Local.objects.filter(condominio=condominio, ativo=True).order_by("ordem", "nome")
    configuracao = getattr(condominio, "configuracao", None)

    return render(
        request,
        "core/agenda.html",
        {
            "condominio": condominio,
            "configuracao": configuracao,
            "locais": locais,
        },
    )
