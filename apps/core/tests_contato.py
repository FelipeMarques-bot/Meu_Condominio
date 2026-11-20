from django.test import SimpleTestCase, override_settings

from .context_processors import _link_suporte_whatsapp


@override_settings(
    PLANO_WHATSAPP="https://wa.me/5511999999999",
    PLANO_WHATSAPP_MENSAGEM="Olá!\n1) Teste grátis\n2) Pagamento",
)
class LinkSuporteTests(SimpleTestCase):
    def test_inclui_mensagem_pronta(self):
        link = _link_suporte_whatsapp()

        self.assertTrue(link.startswith("https://wa.me/5511999999999?text="))
        self.assertIn("Teste%20gr%C3%A1tis", link)
        self.assertIn("1%29", link)

    @override_settings(PLANO_WHATSAPP="https://wa.me/5511999999999?text=antiga")
    def test_respeita_texto_ja_configurado(self):
        self.assertEqual(
            _link_suporte_whatsapp(),
            "https://wa.me/5511999999999?text=antiga",
        )
