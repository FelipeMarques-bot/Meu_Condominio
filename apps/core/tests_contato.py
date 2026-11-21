from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from .context_processors import _link_suporte_landing, _link_suporte_whatsapp


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

    @override_settings(
        PLANO_WHATSAPP="https://wa.me/5511999999999?text=",
        PLANO_WHATSAPP_MENSAGEM="Mensagem padrão",
    )
    def test_completa_texto_vazio_no_link(self):
        self.assertEqual(
            _link_suporte_whatsapp(),
            "https://wa.me/5511999999999?text=Mensagem%20padr%C3%A3o",
        )

    @override_settings(
        PLANO_WHATSAPP="https://wa.me/5511999999999",
        PLANO_WHATSAPP_MENSAGEM="",
    )
    def test_usa_mensagem_padrao_quando_variavel_fica_vazia(self):
        link = _link_suporte_whatsapp()

        self.assertIn("?text=Ol%C3%A1", link)
        self.assertIn("Teste%20gr%C3%A1tis", link)


@override_settings(
    PLANO_WHATSAPP="https://wa.me/5511999999999",
    PLANO_WHATSAPP_MENSAGEM="Mensagem com opções",
    PLANO_WHATSAPP_MENSAGEM_LANDING="Quero conhecer o Meu Condomínio",
)
class BotaoContatoLandingTests(TestCase):
    def test_botao_falar_com_a_gente_usa_mensagem_simples(self):
        resposta = self.client.get(reverse("landing"))

        self.assertContains(
            resposta,
            "https://wa.me/5511999999999?text=Quero%20conhecer%20o%20Meu%20Condom%C3%ADnio",
        )
        self.assertContains(resposta, "Falar com a gente")

    def test_mensagens_do_site_e_do_plano_sao_diferentes(self):
        self.assertNotEqual(
            _link_suporte_landing(),
            _link_suporte_whatsapp(),
        )
        self.assertIn("op%C3%A7%C3%B5es", _link_suporte_whatsapp())
