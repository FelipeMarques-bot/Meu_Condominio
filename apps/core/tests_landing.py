from django.test import TestCase
from django.urls import reverse


class LandingCopyTests(TestCase):
    def test_textos_tecnicos_nao_aparecem(self):
        resposta = self.client.get(reverse("landing"))

        self.assertEqual(resposta.status_code, 200)
        for termo in (
            "SLA",
            "OCR",
            "E2E",
            "Fase 0",
            "piloto",
            "ruído",
            "sem emoji",
            "implantação assistida",
        ):
            self.assertNotContains(resposta, termo)

    def test_chamada_para_teste_usa_linguagem_simples(self):
        resposta = self.client.get(reverse("landing"))

        self.assertContains(resposta, "Organize as reservas do seu condomínio")
        self.assertContains(resposta, "Teste de 14 dias")
        self.assertContains(resposta, "plano-card")
