from calendar import Calendar
from datetime import date, datetime, time, timedelta
from io import BytesIO
from pathlib import Path

import qrcode
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Case, Count, IntegerField, Q, Sum, Value, When
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.formats import date_format

from apps.core.models import ConfiguracaoCondominio
from apps.core.notifications import (
    link_whatsapp,
    notificar_nova_analise,
    notificar_reserva_cancelada,
    notificar_reserva_confirmada,
    notificar_reserva_criada,
    notificar_reserva_rejeitada,
)
from apps.core.permissoes import (
    pode_gerir,
    pode_ver_reserva,
    sindico_required,
    unidades_do_usuario,
)
from apps.pagamentos import abacatepay
from apps.pagamentos.brcode import gerar_payload, gerar_qr_data_uri

from .codigos import gerar_codigo_checkin
from .forms import ComprovanteForm, ListaEsperaForm, ReservaForm
from .models import ListaEspera, Local, Reserva
from .ocr import analisar_comprovante
from .prazos import liberar_lista_espera
from .resultados import resultados_nao_vistos

HOLD_HORAS = 2


def _condominio(request):
    condominio = getattr(request, "condominio", None)
    if condominio is None:
        raise Http404("Condomínio não encontrado.")
    return condominio


def _configuracao(condominio):
    configuracao, _ = ConfiguracaoCondominio.objects.get_or_create(condominio=condominio)
    return configuracao


def _garantir_cobranca_pix(condominio, configuracao, reserva) -> bool:
    if reserva.pix_brcode and not reserva.pix_vencido:
        return True

    try:
        cobranca = abacatepay.criar_cobranca_pix(
            api_key=configuracao.pix_gateway_api_key,
            valor_centavos=int((reserva.valor * 100).to_integral_value()),
            descricao=f"{condominio.nome} · {reserva.local.nome}",
            external_id=str(reserva.pk),
        )
    except abacatepay.ErroAbacatePay:
        return False

    reserva.pix_cobranca_id = cobranca["id"]
    reserva.pix_brcode = cobranca["brcode"]
    reserva.pix_qr_data_uri = cobranca["brcode_base64"] or gerar_qr_data_uri(
        cobranca["brcode"]
    )
    reserva.pix_expira_em = cobranca["expira_em"]
    reserva.save(
        update_fields=[
            "pix_cobranca_id",
            "pix_brcode",
            "pix_qr_data_uri",
            "pix_expira_em",
            "atualizado_em",
        ]
    )
    return True


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
            notificar_reserva_criada(reserva)
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
            "unidades": unidades_do_usuario(request.user, condominio),
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


def _calendario_do_mes(request, condominio, unidades_ids, usuario):
    referencia = _mes_referencia(request.GET.get("mes", ""))
    proximo = (referencia + timedelta(days=32)).replace(day=1)
    anterior = (referencia - timedelta(days=1)).replace(day=1)

    fuso = timezone.get_current_timezone()
    inicio_dt = timezone.make_aware(datetime.combine(referencia, time.min), fuso)
    fim_dt = timezone.make_aware(datetime.combine(proximo, time.min), fuso)

    por_dia: dict[int, list] = {}
    dias_info: dict[str, dict] = {}
    total = 0

    reservas_mes = (
        Reserva.objects.filter(
            condominio=condominio,
            inicio__gte=inicio_dt,
            inicio__lt=fim_dt,
        )
        .exclude(status=Reserva.Status.CANCELADA)
        .select_related("local", "unidade")
        .order_by("inicio")
    )

    for reserva in reservas_mes:
        inicio_local = timezone.localtime(reserva.inicio)
        fim_local = timezone.localtime(reserva.fim)
        propria = (
            reserva.solicitante_id == usuario.id
            or reserva.unidade_id in unidades_ids
        )
        item = {
            "local": reserva.local.nome,
            "horario": f"{inicio_local:%H:%M}–{fim_local:%H:%M}",
            "propria": propria,
            "status": reserva.get_status_display() if propria else "Ocupado",
            "tom": reserva.status if propria else "ocupado",
        }
        por_dia.setdefault(inicio_local.day, []).append(item)
        chave = inicio_local.date().isoformat()
        info = dias_info.setdefault(
            chave,
            {
                "rotulo": date_format(inicio_local, "l, j \\d\\e F").capitalize(),
                "eventos": [],
            },
        )
        info["eventos"].append(item)
        total += 1

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
                    "chave": dia.isoformat() if pertence else "",
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
        "total": total,
        "dias": dias_info,
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
    esperas = ListaEspera.objects.filter(
        condominio=condominio,
        solicitante=request.user,
    ).select_related("local", "unidade")

    return render(
        request,
        "reservas/minhas_reservas.html",
        {
            "condominio": condominio,
            "reservas": reservas,
            "esperas": esperas,
            "resultados_novos": resultados_nao_vistos(request.user, condominio),
            "calendario": _calendario_do_mes(
                request,
                condominio,
                set(unidades.values_list("id", flat=True)),
                request.user,
            ),
        },
    )


@login_required
def marcar_resultados_vistos(request, slug):
    condominio = _condominio(request)
    if request.method != "POST":
        raise Http404
    resultados_nao_vistos(request.user, condominio).update(
        resultado_visto_em=timezone.now()
    )
    return redirect("minhas_reservas", slug=condominio.slug)


@login_required
def reserva_detalhe(request, slug, pk):
    condominio = _condominio(request)
    reserva = _reserva_para_usuario(request, pk)
    configuracao = _configuracao(condominio)

    if (
        not pode_gerir(request.user, condominio)
        and reserva.status in {Reserva.Status.CONFIRMADA, Reserva.Status.REJEITADA}
        and reserva.resultado_visto_em is None
    ):
        reserva.resultado_visto_em = timezone.now()
        reserva.save(update_fields=["resultado_visto_em"])

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
    pix_dinamico = False
    if configuracao.pix_automatico_pronto and reserva.status in {
        Reserva.Status.AGUARDANDO_COMPROVANTE,
        Reserva.Status.EM_ANALISE,
    }:
        pix_dinamico = _garantir_cobranca_pix(condominio, configuracao, reserva)
        if pix_dinamico:
            payload = reserva.pix_brcode
            qr_data_uri = reserva.pix_qr_data_uri

    if not pix_dinamico and configuracao.pix_chave:
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
    elif not pix_dinamico:
        erro_pix = (
            "Não foi possível gerar o Pix automático agora. "
            "Pague pela chave do condomínio e envie o comprovante."
        )

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
            "pix_dinamico": pix_dinamico,
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

    arquivo = form.cleaned_data["comprovante"]
    ocr = analisar_comprovante(arquivo, reserva.valor, timezone.localdate(reserva.inicio))
    reserva.comprovante = arquivo
    reserva.comprovante_enviado_em = agora
    reserva.prazo_analise_em = prazo
    reserva.status = Reserva.Status.EM_ANALISE
    reserva.motivo_rejeicao = ""
    reserva.ocr_status = ocr.situacao
    reserva.ocr_valor = ocr.valor
    reserva.ocr_data = ocr.data
    reserva.ocr_observacao = ocr.observacao
    reserva.ocr_processado_em = agora
    reserva.save(
        update_fields=[
            "comprovante",
            "comprovante_enviado_em",
            "prazo_analise_em",
            "status",
            "motivo_rejeicao",
            "ocr_status",
            "ocr_valor",
            "ocr_data",
            "ocr_observacao",
            "ocr_processado_em",
            "atualizado_em",
        ]
    )

    notificar_nova_analise(reserva)
    if ocr.situacao == Reserva.OcrStatus.VERMELHO:
        messages.warning(
            request,
            "A leitura automática encontrou uma divergência. "
            "O administrador vai conferir o arquivo.",
        )
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
    notificar_reserva_cancelada(reserva)
    liberar_lista_espera(reserva)
    messages.success(request, "Reserva cancelada.")
    return redirect("minhas_reservas", slug=condominio.slug)


@login_required
@sindico_required
def painel(request, slug):
    condominio = _condominio(request)
    reservas = Reserva.objects.filter(condominio=condominio).select_related(
        "local", "unidade", "solicitante"
    )
    prioridade_ocr = Case(
        When(ocr_status=Reserva.OcrStatus.VERMELHO, then=Value(0)),
        When(ocr_status=Reserva.OcrStatus.AMARELO, then=Value(1)),
        When(ocr_status=Reserva.OcrStatus.VERDE, then=Value(2)),
        default=Value(3),
        output_field=IntegerField(),
    )
    pendentes = (
        reservas.filter(
            status__in=[Reserva.Status.AGUARDANDO_COMPROVANTE, Reserva.Status.EM_ANALISE]
        )
        .annotate(ocr_prioridade=prioridade_ocr)
        .order_by("ocr_prioridade", "inicio")
    )
    ocr_vermelhos = sum(
        1 for reserva in pendentes if reserva.ocr_status == Reserva.OcrStatus.VERMELHO
    )
    ocr_amarelos = sum(
        1 for reserva in pendentes if reserva.ocr_status == Reserva.OcrStatus.AMARELO
    )
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
            "ocr_vermelhos": ocr_vermelhos,
            "ocr_amarelos": ocr_amarelos,
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
        {
            "condominio": condominio,
            "reserva": reserva,
            "whatsapp_url": link_whatsapp(
                reserva.solicitante.telefone if reserva.solicitante else "",
                f"Ol\u00e1! Sobre a reserva do {reserva.local.nome} em "
                f"{date_format(reserva.inicio, 'd/m/Y H:i')}.",
            ),
        },
    )


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

    if request.POST.get("confirmo_analise") != "on":
        messages.error(
            request,
            "Confirme que você abriu e conferiu o comprovante antes de aprovar.",
        )
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
        reserva.codigo_checkin = gerar_codigo_checkin(condominio)
        reserva.resultado_visto_em = None
        reserva.save(
            update_fields=[
                "status",
                "confirmado_em",
                "codigo_checkin",
                "resultado_visto_em",
                "atualizado_em",
            ]
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
    reserva.resultado_visto_em = None
    reserva.save(
        update_fields=[
            "status",
            "motivo_rejeicao",
            "resultado_visto_em",
            "atualizado_em",
        ]
    )

    notificar_reserva_rejeitada(reserva)
    messages.success(request, "Comprovante recusado e morador notificado.")
    return redirect("analise_reserva", slug=slug, pk=pk)


@login_required
def entrar_na_espera(request, slug, local_slug):
    condominio = _condominio(request)
    local = get_object_or_404(Local, condominio=condominio, slug=local_slug, ativo=True)

    if request.method != "POST":
        return redirect("reservar", slug=slug, local_slug=local_slug)

    form = ListaEsperaForm(
        request.POST, condominio=condominio, usuario=request.user, local=local
    )
    if not form.is_valid():
        erro = next(iter(form.errors.values()))[0]
        messages.error(request, f"N\u00e3o foi poss\u00edvel entrar na lista: {erro}")
        return redirect("reservar", slug=slug, local_slug=local_slug)

    entrada, criada = ListaEspera.objects.get_or_create(
        condominio=condominio,
        local=local,
        unidade=form.cleaned_data["unidade"],
        data=form.cleaned_data["data"],
        status=ListaEspera.Status.AGUARDANDO,
        defaults={"solicitante": request.user},
    )
    if criada:
        messages.success(
            request,
            "Voc\u00ea entrou na lista de espera. Avisamos por e-mail quando vagar.",
        )
    else:
        messages.info(request, "Voc\u00ea j\u00e1 est\u00e1 na lista para esse dia.")
    return redirect("minhas_reservas", slug=slug)


@login_required
def cancelar_espera(request, slug, pk):
    condominio = _condominio(request)
    entrada = get_object_or_404(ListaEspera, condominio=condominio, pk=pk)
    if entrada.solicitante_id != request.user.id:
        raise PermissionDenied("Esta espera n\u00e3o \u00e9 sua.")

    if request.method == "POST" and entrada.status == ListaEspera.Status.AGUARDANDO:
        entrada.status = ListaEspera.Status.CANCELADO
        entrada.save(update_fields=["status"])
        messages.success(request, "Sa\u00edda da lista de espera registrada.")
    return redirect("minhas_reservas", slug=slug)


@login_required
@sindico_required
def checkin(request, slug):
    condominio = _condominio(request)
    hoje = timezone.localdate()
    fuso = timezone.get_current_timezone()
    inicio = timezone.make_aware(datetime.combine(hoje, time.min), fuso)
    fim = inicio + timedelta(days=1)

    encontrada = None
    if request.method == "POST":
        codigo = request.POST.get("codigo", "").strip().upper()
        encontrada = (
            Reserva.objects.filter(
                condominio=condominio,
                codigo_checkin=codigo,
                status=Reserva.Status.CONFIRMADA,
            )
            .select_related("local", "unidade", "solicitante")
            .first()
        )
        if encontrada is None:
            messages.error(
                request,
                "C\u00f3digo n\u00e3o encontrado entre as reservas confirmadas.",
            )
        elif encontrada.checkin_em:
            messages.info(
                request,
                "Este c\u00f3digo j\u00e1 foi usado em "
                f"{timezone.localtime(encontrada.checkin_em):%d/%m/%Y %H:%M}.",
            )
        elif not encontrada.checkin_foto:
            messages.error(
                request,
                "O morador ainda n\u00e3o confirmou o uso com foto no app. "
                "Pe\u00e7a para ele abrir a reserva e tirar a foto do espa\u00e7o.",
            )
        else:
            encontrada.checkin_em = timezone.now()
            encontrada.checkin_por = request.user
            encontrada.save(
                update_fields=["checkin_em", "checkin_por", "atualizado_em"]
            )
            if encontrada.inicio.date() != hoje:
                messages.warning(
                    request,
                    "Check-in registrado fora do dia da reserva.",
                )
            else:
                messages.success(request, "Check-in confirmado.")

    do_dia = (
        Reserva.objects.filter(
            condominio=condominio,
            status=Reserva.Status.CONFIRMADA,
            inicio__gte=inicio,
            inicio__lt=fim,
        )
        .select_related("local", "unidade", "solicitante")
        .order_by("inicio")
    )

    return render(
        request,
        "reservas/checkin.html",
        {
            "condominio": condominio,
            "reservas": do_dia,
            "encontrada": encontrada,
        },
    )


@login_required
def confirmar_uso(request, slug, pk):
    """Morador confirma o uso do espaço no dia, obrigatoriamente com foto."""
    condominio = _condominio(request)
    reserva = _reserva_para_usuario(request, pk)

    if reserva.status != Reserva.Status.CONFIRMADA:
        messages.error(
            request, "S\u00f3 \u00e9 poss\u00edvel confirmar o uso de uma reserva confirmada."
        )
        return redirect("reserva_detalhe", slug=slug, pk=reserva.pk)

    if reserva.inicio.date() != timezone.localdate():
        messages.error(
            request, "A foto de confirma\u00e7\u00e3o s\u00f3 pode ser enviada no dia da reserva."
        )
        return redirect("reserva_detalhe", slug=slug, pk=reserva.pk)

    if reserva.checkin_em and reserva.checkin_foto:
        messages.info(request, "O uso desta reserva j\u00e1 foi confirmado com foto.")
        return redirect("reserva_detalhe", slug=slug, pk=reserva.pk)

    if request.method == "POST":
        foto = request.FILES.get("foto")
        tipo = (getattr(foto, "content_type", "") or "").lower()
        if foto is None:
            messages.error(request, "Tire uma foto do espa\u00e7o para confirmar o uso.")
        elif not tipo.startswith("image/"):
            messages.error(request, "Envie uma foto em JPG, PNG ou HEIC.")
        else:
            with transaction.atomic():
                reserva.checkin_foto = foto
                reserva.checkin_em = timezone.now()
                reserva.checkin_por = request.user
                reserva.save(
                    update_fields=[
                        "checkin_foto",
                        "checkin_em",
                        "checkin_por",
                        "atualizado_em",
                    ]
                )
            messages.success(
                request, "Uso confirmado com foto. Bom proveito do espa\u00e7o!"
            )
            return redirect("reserva_detalhe", slug=slug, pk=reserva.pk)

    return render(
        request,
        "reservas/confirmar_uso.html",
        {
            "condominio": condominio,
            "reserva": reserva,
        },
    )


@login_required
def reserva_qr(request, slug, pk):
    reserva = _reserva_para_usuario(request, pk)
    if not reserva.codigo_checkin:
        raise Http404

    imagem = qrcode.make(reserva.codigo_checkin)
    buffer = BytesIO()
    imagem.save(buffer, format="PNG")
    resposta = HttpResponse(buffer.getvalue(), content_type="image/png")
    resposta["Cache-Control"] = "private, max-age=300"
    return resposta


@login_required
@sindico_required
def relatorios(request, slug):
    condominio = _condominio(request)
    referencia = _mes_referencia(request.GET.get("mes", ""))
    proximo = (referencia + timedelta(days=32)).replace(day=1)
    fuso = timezone.get_current_timezone()
    inicio = timezone.make_aware(datetime.combine(referencia, time.min), fuso)
    fim = timezone.make_aware(datetime.combine(proximo, time.min), fuso)

    reservas = Reserva.objects.filter(
        condominio=condominio, inicio__gte=inicio, inicio__lt=fim
    )
    confirmadas = reservas.filter(status=Reserva.Status.CONFIRMADA)
    total_confirmado = confirmadas.aggregate(total=Sum("valor"))["total"] or 0
    por_local = (
        confirmadas.values("local__nome")
        .annotate(quantidade=Count("id"), total=Sum("valor"))
        .order_by("-quantidade", "local__nome")
    )
    por_unidade = (
        confirmadas.values("unidade__bloco", "unidade__numero")
        .annotate(quantidade=Count("id"), total=Sum("valor"))
        .order_by("-quantidade")[:10]
    )

    return render(
        request,
        "reservas/relatorios.html",
        {
            "condominio": condominio,
            "mes": referencia,
            "mes_anterior": (referencia - timedelta(days=1)).replace(day=1),
            "mes_seguinte": proximo,
            "total_reservas": reservas.count(),
            "total_confirmadas": confirmadas.count(),
            "total_pendentes": reservas.filter(
                status__in=[
                    Reserva.Status.AGUARDANDO_COMPROVANTE,
                    Reserva.Status.EM_ANALISE,
                ]
            ).count(),
            "total_canceladas": reservas.filter(
                status__in=[Reserva.Status.CANCELADA, Reserva.Status.EXPIRADA]
            ).count(),
            "total_confirmado": total_confirmado,
            "por_local": por_local,
            "por_unidade": por_unidade,
        },
    )
