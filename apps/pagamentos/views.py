import hmac
import json
import logging

from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.core.models import Condominio
from apps.core.notifications import notificar_reserva_confirmada
from apps.pagamentos import abacatepay
from apps.pagamentos.models import EventoPix
from apps.reservas.codigos import gerar_codigo_checkin
from apps.reservas.models import Reserva

logger = logging.getLogger(__name__)

STATUS_PAGOS = {"PAID", "APPROVED"}


def _recusar() -> HttpResponse:
    return HttpResponse(status=401)


@csrf_exempt
@require_POST
def webhook_abacatepay(request, slug, token):
    condominio = Condominio.objects.filter(slug=slug, ativo=True).first()
    if condominio is None:
        return HttpResponse(status=404)

    if len(request.body) > 64 * 1024:
        return HttpResponse(status=413)

    configuracao = getattr(condominio, "configuracao", None)
    if configuracao is None:
        return _recusar()

    segredo = configuracao.pix_gateway_webhook_secret or ""
    if not segredo or not hmac.compare_digest(token, segredo):
        return _recusar()

    assinatura = request.headers.get("X-Webhook-Signature", "")
    if not abacatepay.assinatura_valida(request.body, assinatura):
        return _recusar()

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return _recusar()

    evento_id = str(payload.get("id") or "")
    tipo = str(payload.get("event") or "")
    if not evento_id:
        return _recusar()

    evento, criado = EventoPix.objects.get_or_create(
        condominio=condominio,
        evento_id=evento_id,
        defaults={"tipo": tipo, "payload": payload},
    )
    if not criado:
        return HttpResponse(status=200)

    if tipo != "transparent.completed":
        evento.detalhe = f"Evento {tipo or 'desconhecido'} ignorado."
        evento.save(update_fields=["detalhe"])
        return HttpResponse(status=200)

    dados = payload.get("data") or {}
    cobranca = dados.get("transparent") or {}
    reserva = (
        Reserva.all_objects.filter(
            condominio=condominio, pix_cobranca_id=str(cobranca.get("id") or "")
        )
        .select_related("local")
        .first()
    )
    if reserva is None:
        evento.detalhe = "CobranÃ§a nÃ£o encontrada para este condomÃ­nio."
        evento.save(update_fields=["detalhe"])
        return HttpResponse(status=200)

    valor_centavos = int((reserva.valor * 100).to_integral_value())
    if int(cobranca.get("amount") or 0) != valor_centavos:
        evento.detalhe = "Valor pago diferente do valor da reserva."
        evento.save(update_fields=["detalhe"])
        logger.warning(
            "Webhook AbacatePay com valor divergente na reserva %s", reserva.pk
        )
        return HttpResponse(status=200)

    if str(cobranca.get("status") or "") not in STATUS_PAGOS:
        evento.detalhe = f"Status {cobranca.get('status')} nÃ£o confirma a reserva."
        evento.save(update_fields=["detalhe"])
        return HttpResponse(status=200)

    with transaction.atomic():
        reserva = Reserva.all_objects.select_for_update().get(pk=reserva.pk)
        if reserva.status == Reserva.Status.CONFIRMADA:
            evento.processado = True
            evento.detalhe = "Reserva jÃ¡ estava confirmada."
            evento.save(update_fields=["processado", "detalhe"])
            return HttpResponse(status=200)

        if reserva.status in {
            Reserva.Status.CANCELADA,
            Reserva.Status.EXPIRADA,
        }:
            evento.detalhe = "Reserva cancelada ou expirada; pagamento registrado."
            evento.save(update_fields=["detalhe"])
            return HttpResponse(status=200)

        reserva.status = Reserva.Status.CONFIRMADA
        reserva.confirmado_em = timezone.now()
        reserva.pix_pago_em = timezone.now()
        if not reserva.codigo_checkin:
            reserva.codigo_checkin = gerar_codigo_checkin(condominio)
        reserva.save(
            update_fields=[
                "status",
                "confirmado_em",
                "pix_pago_em",
                "codigo_checkin",
                "atualizado_em",
            ]
        )
        evento.processado = True
        evento.detalhe = "Reserva confirmada pelo Pix."
        evento.save(update_fields=["processado", "detalhe"])

    notificar_reserva_confirmada(reserva)
    return HttpResponse(status=200)
