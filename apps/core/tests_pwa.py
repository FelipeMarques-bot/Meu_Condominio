from django.test import TestCase


class AplicativoTests(TestCase):
    def test_manifest_disponivel_na_raiz(self):
        resposta = self.client.get("/manifest.webmanifest")

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(
            resposta["Content-Type"], "application/manifest+json"
        )
        conteudo = b"".join(resposta.streaming_content).decode()
        self.assertIn('"start_url": "/"', conteudo)
        self.assertIn("/static/pwa/icon-192.png", conteudo)

    def test_service_worker_na_raiz_com_escopo(self):
        resposta = self.client.get("/sw.js")

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta["Service-Worker-Allowed"], "/")
        self.assertIn(
            "meu-condominio", b"".join(resposta.streaming_content).decode()
        )

    def test_pagina_inicial_aponta_para_o_manifesto(self):
        resposta = self.client.get("/")

        self.assertContains(resposta, 'rel="manifest"')
        self.assertContains(resposta, "/static/pwa/apple-touch-icon.png")
