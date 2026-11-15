from decimal import Decimal

from django.test import SimpleTestCase

from .brcode import crc16, gerar_payload, gerar_qr_data_uri


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
