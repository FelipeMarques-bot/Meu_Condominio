from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.reservas.models import Local

from .models import Condominio, ConfiguracaoCondominio
from .notifications import enviar_telegram, telegram_configurado
from .tenancy import reset_current_condominio, set_current_condominio


def criar_condominio(nome: str, slug: str) -> Condominio:
    return Condominio.objects.create(nome=nome, slug=slug)


class ConfiguracaoPadraoTests(TestCase):
    def test_configuracao_criada_com_o_condominio(self):
        condominio = criar_condominio("Bela Vista", "bela-vista")

        configuracao = ConfiguracaoCondominio.objects.get(condominio=condominio)

        self.assertEqual(configuracao.antecedencia_minima_horas, 48)
        self.assertEqual(configuracao.prazo_analise_horas, 24)
        self.assertEqual(configuracao.pix_modo, ConfiguracaoCondominio.PixModo.MANUAL)
        self.assertFalse(configuracao.pix_dinamico_ativo)

    def test_iniciais_ignoram_a_palavra_condominio(self):
        condominio = criar_condominio("Condomínio Bela Vista", "bela-vista")

        self.assertEqual(condominio.iniciais, "BV")

    def test_whatsapp_e_telegram_nascem_desligados(self):
        condominio = criar_condominio("Bela Vista", "bela-vista")
        configuracao = ConfiguracaoCondominio.objects.get(condominio=condominio)

        self.assertEqual(configuracao.whatsapp_url, "")
        self.assertFalse(configuracao.telegram_ativo)


class TelegramTests(TestCase):
    def setUp(self):
        self.condominio = criar_condominio("Bela Vista", "bela-vista")
        self.configuracao = ConfiguracaoCondominio.objects.get(condominio=self.condominio)

    def test_sem_configuracao_nao_envia(self):
        with patch("apps.core.notifications.urllib.request.urlopen") as urlopen:
            self.assertFalse(enviar_telegram(self.condominio, "teste"))
            urlopen.assert_not_called()

    @override_settings(TELEGRAM_BOT_TOKEN="token-de-teste")
    def test_envia_quando_ativo(self):
        self.configuracao.telegram_ativo = True
        self.configuracao.telegram_chat_id = "-100123"
        self.configuracao.save()

        resposta = patch("apps.core.notifications.urllib.request.urlopen")
        with resposta as urlopen:
            urlopen.return_value.__enter__.return_value.status = 200

            self.assertTrue(telegram_configurado(self.condominio))
            self.assertTrue(enviar_telegram(self.condominio, "teste"))
            urlopen.assert_called_once()


class IsolamentoTenantTests(TestCase):
    def setUp(self):
        self.bela_vista = criar_condominio("Bela Vista", "bela-vista")
        self.jardim = criar_condominio("Jardim das Flores", "jardim")
        Local.objects.create(
            condominio=self.bela_vista, nome="Quiosque", slug="quiosque", valor=180
        )
        Local.objects.create(
            condominio=self.jardim, nome="Salão", slug="salao", valor=300
        )

    def test_sem_contexto_retorna_todos(self):
        self.assertEqual(Local.objects.count(), 2)

    def test_com_contexto_filtra_pelo_condominio(self):
        token = set_current_condominio(self.bela_vista)
        try:
            self.assertEqual(Local.objects.count(), 1)
            self.assertEqual(Local.objects.get().nome, "Quiosque")
        finally:
            reset_current_condominio(token)


class PaginasTests(TestCase):
    def setUp(self):
        self.condominio = criar_condominio("Bela Vista", "bela-vista")
        Local.objects.create(
            condominio=self.condominio, nome="Quiosque Primavera", slug="quiosque", valor=180
        )

    def test_landing_responde_200(self):
        resposta = self.client.get(reverse("landing"))

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Meu Condomínio")

    def test_agenda_responde_200_e_lista_locais(self):
        resposta = self.client.get(reverse("agenda", kwargs={"slug": "bela-vista"}))

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Quiosque Primavera")

    def test_condominio_inexistente_retorna_404(self):
        resposta = self.client.get(reverse("agenda", kwargs={"slug": "nao-existe"}))

        self.assertEqual(resposta.status_code, 404)


class WhatsAppContatoTests(TestCase):
    def test_numero_gera_link_com_mensagem_pronta(self):
        condominio = criar_condominio("Bela Vista", "bela-vista")
        configuracao = ConfiguracaoCondominio.objects.get(condominio=condominio)
        configuracao.whatsapp_numero = "(47) 99999-0000"

        self.assertTrue(configuracao.whatsapp_link.startswith("https://wa.me/5547999990000"))
        self.assertIn("text=", configuracao.whatsapp_link)

    def test_link_salvo_e_usado_quando_nao_ha_numero(self):
        condominio = criar_condominio("Bela Vista", "bela-vista")
        configuracao = ConfiguracaoCondominio.objects.get(condominio=condominio)
        configuracao.whatsapp_url = "https://wa.me/5511988887777"

        self.assertEqual(configuracao.whatsapp_link, configuracao.whatsapp_url)


class AdminBrandingTests(TestCase):
    def test_login_do_admin_usa_a_marca_da_plataforma(self):
        resposta = self.client.get(reverse("admin:login"))

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Meu Condomínio")
        self.assertContains(resposta, "Área da equipe")
        self.assertNotContains(resposta, "Django administration")
