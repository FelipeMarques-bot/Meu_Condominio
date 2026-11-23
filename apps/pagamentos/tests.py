import base64
import hashlib
import hmac
import json
import urllib.error
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.models import ConfiguracaoCondominio
from apps.reservas.models import Reserva
from apps.reservas.tests import criar_base, criar_morador, criar_reserva

from . import abacatepay
from .brcode import crc16, gerar_payload, gerar_qr_data_uri
from .models import EventoPix


class BrCodeTests(SimpleTestCase):
    def test_crc16_conhecido(self):
        self.assertEqual(crc16("123456789"), "29B1")

    def test_payload_tem_crc_valido(self):
        payload = gerar_payload(
            "pix@condominio.com.br", "Condomínio Bela Vista", "São Paulo", Decimal("180.00")
        )

        self.assertTrue(payload.startswith("000201"))
        self.assertIn("pix@condominio.com.br", payload)
        self.assertIn("180.00", payload)
        self.assertEqual(payload[-4:], crc16(payload[:-4]))

    def test_payload_remove_acentos(self):
        payload = gerar_payload("chave", "Condomínio Ação", "São Paulo", "10.00")

        self.assertIn("CONDOMINIO ACAO", payload)
        self.assertIn("SAO PAULO", payload)

    def test_qr_gera_data_uri(self):
        payload = gerar_payload("chave", "Condomínio", "Cidade", "10.00")

        self.assertTrue(gerar_qr_data_uri(payload).startswith("data:image/png;base64,"))

    def test_payload_sem_valor_permite_digitar_no_banco(self):
        payload = gerar_payload("chave", "Plataforma", "Brasil")

        self.assertNotIn("5405", payload)
        self.assertEqual(payload[-4:], crc16(payload[:-4]))


class RespostaFalsa:
    def __init__(self, corpo: dict):
        self.corpo = json.dumps(corpo).encode("utf-8")

    def read(self):
        return self.corpo

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class CredencialTests(TestCase):
    def setUp(self):
        self.condominio, _, _ = criar_base()

    def test_segredo_e_gerado_automaticamente(self):
        configuracao = ConfiguracaoCondominio.objects.get(condominio=self.condominio)

        self.assertGreaterEqual(len(configuracao.pix_gateway_webhook_secret), 32)

    def test_chave_e_criptografada_e_recuperada(self):
        configuracao = ConfiguracaoCondominio.objects.get(condominio=self.condominio)
        configuracao.pix_gateway_api_key = "abc_dev_123456"
        configuracao.save()

        configuracao.refresh_from_db()
        self.assertNotIn("abc_dev_123456", configuracao.pix_gateway_api_key_cripto)
        self.assertEqual(configuracao.pix_gateway_api_key, "abc_dev_123456")

    def test_cripto_invalida_vira_chave_vazia(self):
        configuracao = ConfiguracaoCondominio.objects.get(condominio=self.condominio)
        configuracao.pix_gateway_api_key_cripto = "texto-quebrado"
        configuracao.save()

        configuracao.refresh_from_db()
        self.assertEqual(configuracao.pix_gateway_api_key, "")


class ClienteAbacatePayTests(SimpleTestCase):
    def test_cria_cobranca_com_payload_esperado(self):
        capturado = {}

        def fake_abrir(requisicao, timeout):
            capturado["url"] = requisicao.full_url
            capturado["corpo"] = json.loads(requisicao.data.decode("utf-8"))
            capturado["auth"] = requisicao.get_header("Authorization")
            return RespostaFalsa(
                {
                    "success": True,
                    "data": {
                        "id": "pix_char_1",
                        "brCode": "000201...",
                        "brCodeBase64": "iVBORw0KGgo=",
                        "expiresAt": "2026-11-15T23:00:00.000Z",
                        "status": "PENDING",
                    },
                }
            )

        with patch.object(abacatepay, "_abrir", fake_abrir):
            cobranca = abacatepay.criar_cobranca_pix(
                api_key="abc_dev_1",
                valor_centavos=18000,
                descricao="Bela Vista · Quiosque",
                external_id="42",
            )

        self.assertEqual(capturado["url"], "https://api.abacatepay.com/v2/transparents/create")
        self.assertEqual(capturado["auth"], "Bearer abc_dev_1")
        self.assertEqual(capturado["corpo"]["method"], "PIX")
        self.assertEqual(capturado["corpo"]["data"]["amount"], 18000)
        self.assertEqual(capturado["corpo"]["data"]["externalId"], "42")
        self.assertEqual(cobranca["id"], "pix_char_1")
        self.assertTrue(cobranca["brcode_base64"].startswith("data:image/png;base64,"))

    def test_envelope_de_erro_vira_excecao(self):
        with patch.object(
            abacatepay,
            "_abrir",
            lambda *args, **kwargs: RespostaFalsa(
                {"success": False, "error": "Chave inválida"}
            ),
        ):
            with self.assertRaises(abacatepay.ErroAbacatePay):
                abacatepay.criar_cobranca_pix(
                    api_key="x",
                    valor_centavos=100,
                    descricao="teste",
                    external_id="1",
                )

    def test_falha_de_rede_vira_excecao(self):
        def explode(*args, **kwargs):
            raise urllib.error.URLError("sem rede")

        with patch.object(abacatepay, "_abrir", explode):
            with self.assertRaises(abacatepay.ErroAbacatePay):
                abacatepay.criar_cobranca_pix(
                    api_key="x",
                    valor_centavos=100,
                    descricao="teste",
                    external_id="1",
                )

    def test_assinatura_valida(self):
        corpo = b'{"event":"transparent.completed"}'
        assinatura = base64.b64encode(
            hmac.new(
                abacatepay.CHAVE_PUBLICA_WEBHOOK.encode("utf-8"),
                corpo,
                hashlib.sha256,
            ).digest()
        ).decode("ascii")

        self.assertTrue(abacatepay.assinatura_valida(corpo, assinatura))
        self.assertFalse(abacatepay.assinatura_valida(corpo, "outra"))
        self.assertFalse(abacatepay.assinatura_valida(corpo, ""))


class PagamentoDinamicoTests(TestCase):
    def setUp(self):
        self.condominio, self.local, self.unidade = criar_base()
        self.morador = criar_morador(self.unidade)
        self.reserva = criar_reserva(
            self.condominio, self.local, self.unidade, self.morador
        )
        self.configuracao = ConfiguracaoCondominio.objects.get(
            condominio=self.condominio
        )
        self.configuracao.pix_dinamico_ativo = True
        self.configuracao.pix_gateway = ConfiguracaoCondominio.GatewayPix.ABACATEPAY
        self.configuracao.pix_gateway_api_key = "abc_dev_123"
        self.configuracao.save()
        self.client.force_login(self.morador)

    def _cobranca(self):
        return {
            "id": "pix_char_9",
            "brcode": "000201PIX",
            "brcode_base64": "data:image/png;base64,AAAA",
            "expira_em": timezone.now() + timedelta(hours=2),
            "status": "PENDING",
            "dev_mode": True,
        }

    def test_pagina_cria_cobranca_e_guarda_codigo(self):
        with patch.object(
            abacatepay, "criar_cobranca_pix", return_value=self._cobranca()
        ):
            resposta = self.client.get(
                reverse("pagamento", args=[self.condominio.slug, self.reserva.pk])
            )

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "000201PIX")
        self.reserva.refresh_from_db()
        self.assertEqual(self.reserva.pix_cobranca_id, "pix_char_9")
        self.assertTrue(self.reserva.pix_qr_data_uri.startswith("data:image/png"))

    def test_falha_no_gateway_cai_para_pix_manual(self):
        self.configuracao.pix_chave = "pix@condominio.com.br"
        self.configuracao.save()

        with patch.object(
            abacatepay,
            "criar_cobranca_pix",
            side_effect=abacatepay.ErroAbacatePay("falhou"),
        ):
            resposta = self.client.get(
                reverse("pagamento", args=[self.condominio.slug, self.reserva.pk])
            )

        self.assertContains(resposta, "000201")
        self.assertContains(resposta, "pix@condominio.com.br")
        self.reserva.refresh_from_db()
        self.assertEqual(self.reserva.pix_cobranca_id, "")

    def test_cobranca_existente_nao_e_recriada(self):
        self.reserva.pix_cobranca_id = "pix_char_antigo"
        self.reserva.pix_brcode = "000201ANTIGO"
        self.reserva.pix_expira_em = timezone.now() + timedelta(hours=1)
        self.reserva.save()

        with patch.object(abacatepay, "criar_cobranca_pix") as criar:
            resposta = self.client.get(
                reverse("pagamento", args=[self.condominio.slug, self.reserva.pk])
            )

        criar.assert_not_called()
        self.assertContains(resposta, "000201ANTIGO")


class WebhookAbacatePayTests(TestCase):
    def setUp(self):
        self.condominio, self.local, self.unidade = criar_base()
        self.morador = criar_morador(self.unidade)
        self.reserva = criar_reserva(
            self.condominio, self.local, self.unidade, self.morador
        )
        self.reserva.pix_cobranca_id = "pix_char_9"
        self.reserva.save()
        self.configuracao = ConfiguracaoCondominio.objects.get(
            condominio=self.condominio
        )
        self.configuracao.pix_dinamico_ativo = True
        self.configuracao.pix_gateway = ConfiguracaoCondominio.GatewayPix.ABACATEPAY
        self.configuracao.save()
        self.url = reverse(
            "webhook_abacatepay",
            args=[self.condominio.slug, self.configuracao.pix_gateway_webhook_secret],
        )

    def _payload(self, *, evento_id="log_1", valor=18000, status="PAID"):
        return {
            "id": evento_id,
            "event": "transparent.completed",
            "apiVersion": 2,
            "devMode": True,
            "data": {
                "transparent": {
                    "id": "pix_char_9",
                    "amount": valor,
                    "status": status,
                }
            },
        }

    def _enviar(self, payload, *, segredo=None, assinatura=True):
        corpo = json.dumps(payload)
        if assinatura is True:
            assinatura = base64.b64encode(
                hmac.new(
                    abacatepay.CHAVE_PUBLICA_WEBHOOK.encode("utf-8"),
                    corpo.encode("utf-8"),
                    hashlib.sha256,
                ).digest()
            ).decode("ascii")
        token = segredo or self.configuracao.pix_gateway_webhook_secret
        url = reverse("webhook_abacatepay", args=[self.condominio.slug, token])
        return self.client.post(
            url,
            data=corpo,
            content_type="application/json",
            HTTP_X_WEBHOOK_SIGNATURE=assinatura or "",
        )

    def test_pagamento_confirmado_confirma_reserva(self):
        resposta = self._enviar(self._payload())

        self.assertEqual(resposta.status_code, 200)
        self.reserva.refresh_from_db()
        self.assertEqual(self.reserva.status, Reserva.Status.CONFIRMADA)
        self.assertIsNotNone(self.reserva.pix_pago_em)
        self.assertTrue(self.reserva.codigo_checkin)
        evento = EventoPix.objects.get(condominio=self.condominio)
        self.assertTrue(evento.processado)

    def test_evento_repetido_nao_processa_duas_vezes(self):
        self._enviar(self._payload())
        resposta = self._enviar(self._payload())

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(EventoPix.objects.count(), 1)

    def test_segredo_errado_recusa(self):
        resposta = self._enviar(self._payload(), segredo="segredo-errado")

        self.assertEqual(resposta.status_code, 401)
        self.reserva.refresh_from_db()
        self.assertEqual(self.reserva.status, Reserva.Status.AGUARDANDO_COMPROVANTE)

    def test_assinatura_invalida_recusa(self):
        resposta = self._enviar(self._payload(), assinatura="assinatura-falsa")

        self.assertEqual(resposta.status_code, 401)

    def test_valor_divergente_nao_confirma(self):
        resposta = self._enviar(self._payload(valor=100))

        self.assertEqual(resposta.status_code, 200)
        self.reserva.refresh_from_db()
        self.assertEqual(self.reserva.status, Reserva.Status.AGUARDANDO_COMPROVANTE)

    def test_evento_ignorado_nao_confirma(self):
        payload = self._payload()
        payload["event"] = "transparent.refunded"

        resposta = self._enviar(payload)

        self.assertEqual(resposta.status_code, 200)
        self.reserva.refresh_from_db()
        self.assertEqual(self.reserva.status, Reserva.Status.AGUARDANDO_COMPROVANTE)
