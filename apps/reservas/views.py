import secrets
from calendar import Calendar
from datetime import date, datetime, time, timedelta
from pathlib import Path

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.formats import date_format

from apps.core.models import ConfiguracaoCondominio
from apps.core.notifications import (
    notificar_nova_analise,
    notificar_reserva_confirmada,
    notificar_reserva_rejeitada,
)
from apps.core.permissoes import (
    pode_ver_reserva,
    sindico_required,
    unidades_do_usuario,
)
from apps.pagamentos.brcode import gerar_payload, gerar_qr_data_uri

from .forms import ComprovanteForm, ReservaForm
from .models import Local, Reserva

ALFABETO_CHECKIN = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
HOLD_HORAS = 2


def _condominio(request):
    condominio = getattr(request, "condominio", None)
    if condominio is None:
        raise Http404("Condomínio não encontrado.")
    return condominio


def _configuracao(condominio):
    configuracao, _ = ConfiguracaoCondominio.objects.get_or_create(condominio=condominio)
    return configuracao


def _reserva_para_usuario(request, pk):
    condominio = _condominio(request)
    reserva = get_object_or_404(
        Reserva.objects.select_related("local", "unidade", "solicitante", "condominio"),
        pk=pk,
    )
    if reserva.condominio_id != condominio.pk:
        raise Http404
    if not pode_ver_reserva(request.user, reserva):
        raise PermissionDenied("Você não tem acesso a esta reserva.")
    return reserva


@login_required
def reservar(request, slug, local_slug):
    condominio = _condominio(request)
    local = get_object_or_404(
        Local, condominio=condominio, slug=local_slug, ativo=True
    )
    configuracao = _configuracao(condominio)

    if request.method == "POST":
        form = ReservaForm(
            request.POST,
            condominio=condominio,
            usuario=request.user,
            local=local,
        )
        if form.is_valid():
            agora = timezone.now()
            reserva = Reserva.objects.create(
                condominio=condominio,
                local=local,
                unidade=form.cleaned_data["unidade"],
                solicitante=request.user,
                inicio=form.cleaned_data["inicio"],
                fim=form.cleaned_data["fim"],
                valor=local.valor,
                expira_em=agora + timedelta(hours=HOLD_HORAS),
            )
            messages.success(
                request,
                "Horário reservado por 2 horas. Envie o comprovante para entrar na análise.",
            )
            return redirect("pagamento", slug=slug, pk=reserva.pk)
    else:
        form = ReservaForm(
            condominio=condominio,
            usuario=request.user,
            local=local,
        )

    return render(
        request,
        "reservas/reservar.html",
        {
            "condominio": condominio,
            "local": local,
            "configuracao": configuracao,
            "form": form,
        },
    )


def _mes_referencia(valor: str) -> date:
    hoje = timezone.localdate()
    if valor:
        try:
            ano, mes = (int(parte) for parte in valor.split("-", 1))
            return date(ano, mes, 1)
        except (TypeError, ValueError):
            pass
    return hoje.replace(day=1)


def _calendario_do_mes(request, reservas):
    referencia = _mes_referencia(request.GET.get("mes", ""))
    proximo = (referencia + timedelta(days=32)).replace(day=1)
    anterior = (referencia - timedelta(days=1)).replace(day=1)

    fuso = timezone.get_current_timezone()
    inicio_dt = timezone.make_aware(datetime.combine(referencia, time.min), fuso)
    fim_dt = timezone.make_aware(datetime.combine(proximo, time.min), fuso)

    por_dia: dict[int, list] = {}
    for reserva in reservas.filter(inicio__gte=inicio_dt, inicio__lt=fim_dt):
        dia = timezone.localtime(reserva.inicio).day
        por_dia.setdefault(dia, []).append(reserva)
    for lista in por_dia.values():
        lista.sort(key=lambda reserva: reserva.inicio)

    hoje = timezone.localdate()
    semanas = []
    for semana in Calendar(firstweekday=6).monthdatescalendar(
        referencia.year, referencia.month
    ):
        linha = []
        for dia in semana:
            pertence = dia.month == referencia.month and dia.year == referencia.year
            linha.append(
                {
                    "data": dia,
                    "numero": dia.day,
                    "no_mes": pertence,
                    "hoje": dia == hoje,
                    "reservas": por_dia.get(dia.day, []) if pertence else [],
                }
            )
        semanas.append(linha)

    return {
        "titulo": date_format(referencia, "F \\d\\e Y").capitalize(),
        "valor": referencia.strftime("%Y-%m"),
        "anterior": anterior.strftime("%Y-%m"),
        "proximo": proximo.strftime("%Y-%m"),
        "no_mes_atual": referencia == hoje.replace(day=1),
        "semanas": semanas,
        "total": sum(len(lista) for lista in por_dia.values()),
    }


@login_required
def minhas_reservas(request, slug):
    condominio = _condominio(request)
    unidades = unidades_do_usuario(request.user, condominio)
    reservas = (
        Reserva.objects.filter(
            Q(solicitante=request.user) | Q(unidade__in=unidades)
        )
        .select_related("local", "unidade")
        .distinct()
    )

    return render(
        request,
        "reservas/minhas_reservas.html",
        {
            "condominio": condominio,
            "reservas": reservas,
            "calendario": _calendario_do_mes(request, reservas),
        },
    )


@login_required
def reserva_detalhe(request, slug, pk):
    condominio = _condominio(request)
    reserva = _reserva_para_usuario(request, pk)
    configuracao = _configuracao(condominio)

    return render(
        request,
        "reservas/detalhe.html",
        {
            "condominio": condominio,
            "configuracao": configuracao,
            "reserva": reserva,
        },
    )


@login_required
def pagamento(request, slug, pk):
    condominio = _condominio(request)
    reserva = _reserva_para_usuario(request, pk)
    configuracao = _configuracao(condominio)

    payload = None
    qr_data_uri = None
    erro_pix = None
    if configuracao.pix_chave:
        try:
            payload = gerar_payload(
                configuracao.pix_chave,
                configuracao.pix_beneficiario or condominio.nome,
                configuracao.pix_cidade or "BRASIL",
                reserva.valor,
            )
            qr_data_uri = gerar_qr_data_uri(payload)
        except ValueError:
            erro_pix = "O Pix do condomínio ainda não está configurado."

    return render(
        request,
        "reservas/pagamento.html",
        {
            "condominio": condominio,
            "configuracao": configuracao,
            "reserva": reserva,
            "form": ComprovanteForm(),
            "payload": payload,
            "qr_data_uri": qr_data_uri,
            "erro_pix": erro_pix,
        },
    )


@login_required
def enviar_comprovante(request, slug, pk):
    condominio = _condominio(request)
    reserva = _reserva_para_usuario(request, pk)
    configuracao = _configuracao(condominio)

    if request.method != "POST":
        return redirect("pagamento", slug=slug, pk=reserva.pk)

    if not reserva.pode_receber_comprovante:
        messages.error(request, "Esta reserva não aceita um novo comprovante.")
        return redirect("reserva_detalhe", slug=slug, pk=reserva.pk)

    if reserva.hold_vencido:
        reserva.status = Reserva.Status.EXPIRADA
        reserva.save(update_fields=["status", "atualizado_em"])
        messages.error(
            request,
            "O prazo de 2 horas para enviar o comprovante expirou. Faça uma nova reserva.",
        )
        return redirect("minhas_reservas", slug=slug)

    form = ComprovanteForm(request.POST, request.FILES)
    if not form.is_valid():
        for erro in form.errors.get("comprovante", []):
            messages.error(request, erro)
        return redirect("pagamento", slug=slug, pk=reserva.pk)

    agora = timezone.now()
    limite = agora + timedelta(hours=configuracao.prazo_analise_horas)
    limite_inicio = reserva.inicio - timedelta(hours=2)
    prazo = max(agora + timedelta(minutes=5), min(limite, limite_inicio))

    reserva.comprovante = form.cleaned_data["comprovante"]
    reserva.comprovante_enviado_em = agora
    reserva.prazo_analise_em = prazo
    reserva.status = Reserva.Status.EM_ANALISE
    reserva.motivo_rejeicao = ""
    reserva.save(
        update_fields=[
            "comprovante",
            "comprovante_enviado_em",
            "prazo_analise_em",
            "status",
            "motivo_rejeicao",
            "atualizado_em",
        ]
    )

    notificar_nova_analise(reserva)
    messages.success(
        request,
        "Comprovante recebido. O administrador foi notificado e tem até "
        f"{configuracao.prazo_analise_horas} horas para analisar.",
    )
    return redirect("reserva_detalhe", slug=slug, pk=reserva.pk)


@login_required
def baixar_comprovante(request, slug, pk):
    reserva = _reserva_para_usuario(request, pk)
    if not reserva.comprovante:
        raise Http404("Esta reserva ainda não tem comprovante.")

    arquivo = reserva.comprovante.open("rb")
    return FileResponse(
        arquivo,
        as_attachment=False,
        filename=Path(reserva.comprovante.name).name,
    )


@login_required
def cancelar_reserva(request, slug, pk):
    condominio = _condominio(request)
    reserva = _reserva_para_usuario(request, pk)

    if request.method != "POST":
        return redirect("reserva_detalhe", slug=slug, pk=reserva.pk)

    if reserva.status not in {
        Reserva.Status.AGUARDANDO_COMPROVANTE,
        Reserva.Status.EM_ANALISE,
        Reserva.Status.REJEITADA,
    }:
        messages.error(request, "Esta reserva não pode mais ser cancelada.")
        return redirect("reserva_detalhe", slug=slug, pk=reserva.pk)

    reserva.status = Reserva.Status.CANCELADA
    reserva.save(update_fields=["status", "atualizado_em"])
    messages.success(request, "Reserva cancelada.")
    return redirect("minhas_reservas", slug=condominio.slug)


@login_required
@sindico_required
def painel(request, slug):
    condominio = _condominio(request)
    reservas = Reserva.objects.filter(condominio=condominio).select_related(
        "local", "unidade", "solicitante"
    )
    pendentes = reservas.filter(
        status__in=[Reserva.Status.AGUARDANDO_COMPROVANTE, Reserva.Status.EM_ANALISE]
    ).order_by("inicio")
    confirmadas = reservas.filter(status=Reserva.Status.CONFIRMADA).count()
    agora = timezone.now()
    proximas = reservas.filter(
        status=Reserva.Status.CONFIRMADA,
        inicio__gte=agora,
    ).order_by("inicio")[:5]

    return render(
        request,
        "reservas/painel.html",
        {
            "condominio": condominio,
            "pendentes": pendentes,
            "proximas": proximas,
            "total_confirmadas": confirmadas,
            "sla_vencido": sum(1 for reserva in pendentes if reserva.prazo_vencido),
        },
    )


@login_required
@sindico_required
def analise_reserva(request, slug, pk):
    condominio = _condominio(request)
    reserva = get_object_or_404(
        Reserva.objects.select_related("local", "unidade", "solicitante"),
        pk=pk,
        condominio=condominio,
    )

    return render(
        request,
        "reservas/analise.html",
        {"condominio": condominio, "reserva": reserva},
    )


def _gerar_codigo_checkin(condominio) -> str:
    for _ in range(20):
        codigo = "".join(secrets.choice(ALFABETO_CHECKIN) for _ in range(6))
        if not Reserva.all_objects.filter(
            condominio=condominio, codigo_checkin=codigo
        ).exists():
            return codigo
    return secrets.token_hex(3).upper()


@login_required
@sindico_required
def confirmar_reserva(request, slug, pk):
    condominio = _condominio(request)
    reserva = get_object_or_404(Reserva, pk=pk, condominio=condominio)

    if request.method != "POST":
        return redirect("analise_reserva", slug=slug, pk=pk)

    if reserva.status != Reserva.Status.EM_ANALISE or not reserva.comprovante:
        messages.error(request, "Esta reserva não está pronta para confirmação.")
        return redirect("analise_reserva", slug=slug, pk=pk)

    conflito = (
        Reserva.objects.filter(
            local=reserva.local,
            status=Reserva.Status.CONFIRMADA,
        )
        .exclude(pk=reserva.pk)
        .filter(inicio__lt=reserva.fim, fim__gt=reserva.inicio)
        .exists()
    )
    if conflito:
        messages.error(request, "Já existe outra reserva confirmada neste horário.")
        return redirect("analise_reserva", slug=slug, pk=pk)

    with transaction.atomic():
        reserva.status = Reserva.Status.CONFIRMADA
        reserva.confirmado_em = timezone.now()
        reserva.codigo_checkin = _gerar_codigo_checkin(condominio)
        reserva.save(
            update_fields=["status", "confirmado_em", "codigo_checkin", "atualizado_em"]
        )

    notificar_reserva_confirmada(reserva)
    messages.success(request, "Reserva confirmada e morador notificado.")
    return redirect("painel", slug=slug)


@login_required
@sindico_required
def rejeitar_reserva(request, slug, pk):
    condominio = _condominio(request)
    reserva = get_object_or_404(Reserva, pk=pk, condominio=condominio)

    if request.method != "POST":
        return redirect("analise_reserva", slug=slug, pk=pk)

    motivo = request.POST.get("motivo", "").strip()
    if not motivo:
        messages.error(request, "Informe o motivo da recusa.")
        return redirect("analise_reserva", slug=slug, pk=pk)

    reserva.status = Reserva.Status.REJEITADA
    reserva.motivo_rejeicao = motivo[:1000]
    reserva.save(update_fields=["status", "motivo_rejeicao", "atualizado_em"])

    notificar_reserva_rejeitada(reserva)
    messages.success(request, "Comprovante recusado e morador notificado.")
    return redirect("analise_reserva", slug=slug, pk=pk)
