import json
from unittest.mock import patch

from django.core import mail
from django.test import SimpleTestCase, override_settings

from .email import enviar_email


class RespostaFalsa:
    status = 201

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@override_settings(
    EMAIL_API_PROVIDER="brevo",
    EMAIL_API_KEY="chave",
    DEFAULT_FROM_EMAIL="Meu Condomínio <no-reply@example.com>",
)
class BrevoTests(SimpleTestCase):
    @patch("apps.core.email.urllib.request.urlopen")
    def test_envia_pela_api_brevo(self, urlopen):
        urlopen.return_value = RespostaFalsa()

        enviado = enviar_email("Assunto", "Corpo", ["ana@example.com"])

        self.assertTrue(enviado)
        requisicao = urlopen.call_args.args[0]
        dados = json.loads(requisicao.data)
        self.assertEqual(requisicao.full_url, "https://api.brevo.com/v3/smtp/email")
        self.assertEqual(dados["sender"]["email"], "no-reply@example.com")
        self.assertEqual(dados["to"], [{"email": "ana@example.com"}])
        self.assertEqual(dados["textContent"], "Corpo")


@override_settings(
    EMAIL_API_PROVIDER="resend",
    EMAIL_API_KEY="chave",
    DEFAULT_FROM_EMAIL="Meu Condomínio <no-reply@example.com>",
)
class ResendTests(SimpleTestCase):
    @patch("apps.core.email.urllib.request.urlopen")
    def test_envia_pela_api_resend(self, urlopen):
        urlopen.return_value = RespostaFalsa()

        enviado = enviar_email("Assunto", "Corpo", ["ana@example.com"])

        self.assertTrue(enviado)
        requisicao = urlopen.call_args.args[0]
        dados = json.loads(requisicao.data)
        self.assertEqual(requisicao.full_url, "https://api.resend.com/emails")
        self.assertEqual(dados["from"], "Meu Condomínio <no-reply@example.com>")
        self.assertEqual(dados["to"], ["ana@example.com"])


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    EMAIL_API_PROVIDER="",
    EMAIL_API_KEY="",
    EMAIL_HOST="",
)
class SemApiTests(SimpleTestCase):
    def test_usa_smtp_quando_api_nao_configurada(self):
        enviado = enviar_email("Assunto", "Corpo", ["ana@example.com"])

        self.assertTrue(enviado)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["ana@example.com"])
