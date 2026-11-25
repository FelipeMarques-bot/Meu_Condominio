import tempfile
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Reserva
from .ocr import ResultadoOCR, _classificar, analisar_comprovante
from .tests import criar_base, criar_morador, criar_reserva, criar_sindico


class ClassificacaoOCRTests(TestCase):
    def setUp(self):
        self.valor = Decimal("180.00")
        self.data = date(2026, 11, 25)

    def test_valor_data_e_pagamento_conferem(self):
        resultado = _classificar(
            "Comprovante de Pix\nValor: R$ 180,00\nData: 25/11/2026",
            self.valor,
            self.data,
        )
        self.assertEqual(resultado.situacao, Reserva.OcrStatus.VERDE)
        self.assertEqual(resultado.valor, self.valor)
        self.assertEqual(resultado.data, self.data)

    def test_valor_com_milhar_e_conferido(self):
        resultado = _classificar(
            "Pix enviado\nR$ 1.180,00\n25/11/2026", Decimal("1180.00"), self.data
        )
        self.assertEqual(resultado.situacao, Reserva.OcrStatus.VERDE)
        self.assertEqual(resultado.valor, Decimal("1180.00"))

    def test_valor_divergente_vai_para_vermelho(self):
        resultado = _classificar("Pix R$ 90,00 25/11/2026", self.valor, self.data)
        self.assertEqual(resultado.situacao, Reserva.OcrStatus.VERMELHO)
        self.assertEqual(resultado.valor, Decimal("90.00"))
        self.assertIn("90,00", resultado.observacao)

    def test_data_divergente_vai_para_vermelho(self):
        resultado = _classificar("Pix R$ 180,00 20/11/2026", self.valor, self.data)
        self.assertEqual(resultado.situacao, Reserva.OcrStatus.VERMELHO)
        self.assertEqual(resultado.data, date(2026, 11, 20))

    def test_sem_valor_fica_amarelo(self):
        resultado = _classificar("Pix realizado em 25/11/2026", self.valor, self.data)
        self.assertEqual(resultado.situacao, Reserva.OcrStatus.AMARELO)
        self.assertIsNone(resultado.valor)

    def test_sem_data_fica_amarelo(self):
        resultado = _classificar("Pix R$ 180,00", self.valor, self.data)
        self.assertEqual(resultado.situacao, Reserva.OcrStatus.AMARELO)
        self.assertEqual(resultado.valor, self.valor)

    def test_sem_indicio_de_pagamento_fica_amarelo(self):
        resultado = _classificar("R$ 180,00 25/11/2026", self.valor, self.data)
        self.assertEqual(resultado.situacao, Reserva.OcrStatus.AMARELO)

    def test_sem_texto_fica_amarelo(self):
        resultado = _classificar("   ", self.valor, self.data)
        self.assertEqual(resultado.situacao, Reserva.OcrStatus.AMARELO)


class LeituraOCRTests(TestCase):
    def test_desativada_nao_tenta_ler(self):
        with (
            override_settings(OCR_ATIVO=False),
            patch("apps.reservas.ocr._texto_do_arquivo") as ler,
        ):
            resultado = analisar_comprovante(
                SimpleUploadedFile("a.png", b"x", content_type="image/png"),
                Decimal("180.00"),
                date(2026, 11, 25),
            )
        self.assertEqual(resultado.situacao, Reserva.OcrStatus.AMARELO)
        ler.assert_not_called()

    def test_falha_do_tesseract_nao_interrompe_o_envio(self):
        with (
            self.assertLogs("apps.reservas.ocr", level="INFO"),
            patch("apps.reservas.ocr._texto_do_arquivo", side_effect=RuntimeError),
        ):
            resultado = analisar_comprovante(
                SimpleUploadedFile("a.png", b"x", content_type="image/png"),
                Decimal("180.00"),
                date(2026, 11, 25),
            )
        self.assertEqual(resultado.situacao, Reserva.OcrStatus.AMARELO)
        self.assertIn("indisponível", resultado.observacao)


class FluxoOCRTests(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.override_media = override_settings(MEDIA_ROOT=self.media)
        self.override_media.enable()
        self.addCleanup(self.override_media.disable)

        self.condominio, self.local, self.unidade = criar_base()
        self.morador = criar_morador(self.unidade)
        self.sindico = criar_sindico(self.condominio, self.unidade)
        self.reserva = criar_reserva(self.condominio, self.local, self.unidade, self.morador)
        self.client.force_login(self.morador)

    def _arquivo(self):
        return SimpleUploadedFile(
            "comprovante.png",
            b"\x89PNG\r\n\x1a\nconteudo-fake",
            content_type="image/png",
        )

    def test_envio_grava_classificacao_e_valores_do_ocr(self):
        resultado = ResultadoOCR(
            situacao=Reserva.OcrStatus.VERMELHO,
            valor=Decimal("90.00"),
            data=timezone.localdate(self.reserva.inicio),
            observacao="Valor divergente.",
        )
        with patch("apps.reservas.views.analisar_comprovante", return_value=resultado):
            self.client.post(
                reverse(
                    "enviar_comprovante",
                    kwargs={"slug": self.condominio.slug, "pk": self.reserva.pk},
                ),
                {"comprovante": self._arquivo()},
            )

        self.reserva.refresh_from_db()
        self.assertEqual(self.reserva.status, Reserva.Status.EM_ANALISE)
        self.assertEqual(self.reserva.ocr_status, Reserva.OcrStatus.VERMELHO)
        self.assertEqual(self.reserva.ocr_valor, Decimal("90.00"))
        self.assertEqual(self.reserva.ocr_observacao, "Valor divergente.")
        self.assertIsNotNone(self.reserva.ocr_processado_em)

    def test_painel_ordena_divergentes_primeiro_e_mostra_selo(self):
        self.reserva.ocr_status = Reserva.OcrStatus.VERDE
        self.reserva.save(update_fields=["ocr_status"])
        divergente = criar_reserva(self.condominio, self.local, self.unidade, self.morador)
        divergente.ocr_status = Reserva.OcrStatus.VERMELHO
        divergente.save(update_fields=["ocr_status"])

        self.client.force_login(self.sindico)
        resposta = self.client.get(reverse("painel", kwargs={"slug": self.condominio.slug}))

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(list(resposta.context["pendentes"])[0].pk, divergente.pk)
        self.assertEqual(resposta.context["ocr_vermelhos"], 1)
        self.assertContains(resposta, "Leitura: divergente")

    def test_pagina_de_analise_mostra_o_que_o_ocr_leu(self):
        self.reserva.status = Reserva.Status.EM_ANALISE
        self.reserva.comprovante = "comprovantes/teste.png"
        self.reserva.ocr_status = Reserva.OcrStatus.AMARELO
        self.reserva.ocr_valor = Decimal("90.00")
        self.reserva.ocr_observacao = "Valor lido não confere."
        self.reserva.save(
            update_fields=[
                "status",
                "comprovante",
                "ocr_status",
                "ocr_valor",
                "ocr_observacao",
            ]
        )

        self.client.force_login(self.sindico)
        resposta = self.client.get(
            reverse(
                "analise_reserva",
                kwargs={"slug": self.condominio.slug, "pk": self.reserva.pk},
            )
        )

        self.assertContains(resposta, "Leitura automática: Conferir")
        self.assertContains(resposta, "R$ 90,00")
        self.assertContains(resposta, "Valor lido não confere.")

    def test_reserva_sem_ocr_mantem_instrucao_manual(self):
        self.reserva.status = Reserva.Status.EM_ANALISE
        self.reserva.comprovante = "comprovantes/teste.png"
        self.reserva.save(update_fields=["status", "comprovante"])

        self.client.force_login(self.sindico)
        resposta = self.client.get(
            reverse(
                "analise_reserva",
                kwargs={"slug": self.condominio.slug, "pk": self.reserva.pk},
            )
        )
        self.assertContains(resposta, "Confira o comprovante")
