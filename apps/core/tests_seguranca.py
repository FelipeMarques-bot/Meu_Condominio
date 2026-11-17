import io
import os
from unittest.mock import patch

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from apps.reservas.forms import ComprovanteForm
from apps.usuarios.models import Usuario

from .models import Plano

SENHA = "Senha-Forte-2026"


class ConfiguracaoSeguraTests(SimpleTestCase):
    def test_cabecalhos_e_cookies_endurecidos(self):
        from django.conf import settings

        self.assertEqual(settings.X_FRAME_OPTIONS, "DENY")
        self.assertTrue(settings.SECURE_CONTENT_TYPE_NOSNIFF)
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)
        self.assertTrue(settings.CSRF_COOKIE_HTTPONLY)
        self.assertEqual(settings.SESSION_COOKIE_SAMESITE, "Lax")
        self.assertEqual(settings.CSRF_COOKIE_SAMESITE, "Lax")
        self.assertEqual(settings.DATA_UPLOAD_MAX_MEMORY_SIZE, 6 * 1024 * 1024)

    def test_url_do_admin_vem_do_ambiente(self):
        from django.conf import settings

        self.assertTrue(settings.ADMIN_URL.endswith("/"))

    def test_comprovante_recusa_conteudo_forjado(self):
        arquivo = SimpleUploadedFile(
            "comprovante.png", b"<script>alert(1)</script>", content_type="image/png"
        )
        form = ComprovanteForm(files={"comprovante": arquivo})

        self.assertFalse(form.is_valid())
        self.assertIn("formato informado", str(form.errors))

    def test_comprovante_aceita_assinatura_real(self):
        arquivo = SimpleUploadedFile(
            "comprovante.png", b"\x89PNG\r\n\x1a\nconteudo", content_type="image/png"
        )
        form = ComprovanteForm(files={"comprovante": arquivo})

        self.assertTrue(form.is_valid(), form.errors)


class LoginComLimiteTests(TestCase):
    def setUp(self):
        cache.clear()
        self.usuario = Usuario.objects.create_user(
            username="morador", email="morador@example.com", password=SENHA
        )
        self.client = Client()

    def tearDown(self):
        cache.clear()

    def _errar(self, vezes):
        for _ in range(vezes):
            self.client.post(
                reverse("login"), {"username": "morador", "password": "errada-123"}
            )

    def test_bloqueia_depois_de_cinco_falhas(self):
        self._errar(5)

        resposta = self.client.post(
            reverse("login"), {"username": "morador", "password": SENHA}
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Muitas tentativas de login")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_valido_funciona_antes_do_limite(self):
        self._errar(2)

        resposta = self.client.post(
            reverse("login"), {"username": "morador", "password": SENHA}
        )

        self.assertEqual(resposta.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)


class PlanoTests(TestCase):
    def test_planos_do_catalogo_foram_criados(self):
        self.assertTrue(Plano.objects.filter(slug="essencial").exists())
        self.assertTrue(Plano.objects.filter(slug="rede").exists())

    def test_sugestao_cresce_com_a_quantidade(self):
        self.assertEqual(Plano.para_quantidade(1).slug, "essencial")
        self.assertEqual(Plano.para_quantidade(20).slug, "essencial")
        self.assertEqual(Plano.para_quantidade(21).slug, "conforto")
        self.assertEqual(Plano.para_quantidade(50).slug, "conforto")
        self.assertEqual(Plano.para_quantidade(51).slug, "pro")
        self.assertEqual(Plano.para_quantidade(120).slug, "pro")
        self.assertEqual(Plano.para_quantidade(121).slug, "rede")
        self.assertEqual(Plano.para_quantidade(5000).slug, "rede")

    def test_precos_sobem_com_o_tamanho(self):
        precos = list(Plano.objects.order_by("ordem").values_list("preco_mensal", flat=True))

        self.assertEqual(precos, sorted(precos))


class SuperusuarioPorAmbienteTests(TestCase):
    def test_cria_superusuario_com_variaveis_de_ambiente(self):
        ambiente = {
            "DJANGO_SUPERUSER_USERNAME": "dono",
            "DJANGO_SUPERUSER_EMAIL": "dono@example.com",
            "DJANGO_SUPERUSER_PASSWORD": "Senha-Super-Forte-2026",
        }
        with patch.dict(os.environ, ambiente, clear=True):
            call_command("garantir_superusuario", stdout=io.StringIO())

        usuario = Usuario.objects.get(username="dono")
        self.assertTrue(usuario.is_superuser)
        self.assertTrue(usuario.is_staff)
        self.assertTrue(usuario.check_password("Senha-Super-Forte-2026"))

    def test_e_idempotente(self):
        ambiente = {
            "DJANGO_SUPERUSER_USERNAME": "dono",
            "DJANGO_SUPERUSER_PASSWORD": "Senha-Super-Forte-2026",
        }
        with patch.dict(os.environ, ambiente, clear=True):
            call_command("garantir_superusuario", stdout=io.StringIO())
            call_command("garantir_superusuario", stdout=io.StringIO())

        self.assertEqual(Usuario.objects.filter(username="dono").count(), 1)

    def test_senha_do_superusuario_acompanha_o_ambiente(self):
        Usuario.objects.create_superuser(
            username="dono", email="", password="Senha-Antiga-2026"
        )
        ambiente = {
            "DJANGO_SUPERUSER_USERNAME": "dono",
            "DJANGO_SUPERUSER_PASSWORD": "Senha-Super-Forte-2026",
        }
        with patch.dict(os.environ, ambiente, clear=True):
            call_command("garantir_superusuario", stdout=io.StringIO())

        usuario = Usuario.objects.get(username="dono")
        self.assertTrue(usuario.check_password("Senha-Super-Forte-2026"))

    def test_sem_variaveis_nao_cria_nada(self):
        ambiente = {
            "DJANGO_SUPERUSER_USERNAME": "",
            "DJANGO_SUPERUSER_EMAIL": "",
            "DJANGO_SUPERUSER_PASSWORD": "",
        }
        with patch.dict(os.environ, ambiente, clear=True):
            call_command("garantir_superusuario", stdout=io.StringIO())

        self.assertFalse(Usuario.objects.filter(is_superuser=True).exists())
