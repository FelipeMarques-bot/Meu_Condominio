from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Condominio
from apps.reservas.models import Local

from .models import Convite, Unidade, Usuario, VinculoUnidade

SENHA = "Convite-Forte-2026"


def criar_base(slug="bela-vista"):
    condominio = Condominio.objects.create(nome="Bela Vista", slug=slug)
    Local.objects.create(
        condominio=condominio, nome="Quiosque", slug="quiosque", valor="180.00"
    )
    unidade = Unidade.objects.create(condominio=condominio, bloco="A", numero="101")
    return condominio, unidade


def criar_sindico(unidade, username="sindico"):
    usuario = Usuario.objects.create_user(
        username=username, email=f"{username}@example.com", password=SENHA
    )
    VinculoUnidade.objects.create(
        usuario=usuario, unidade=unidade, papel=VinculoUnidade.Papel.SINDICO
    )
    return usuario


class ConviteAdminTests(TestCase):
    def setUp(self):
        self.condominio, self.unidade = criar_base()
        self.sindico = criar_sindico(self.unidade)
        self.client.force_login(self.sindico)

    def test_pagina_de_convites_abre(self):
        resposta = self.client.get(
            reverse("convites", kwargs={"slug": self.condominio.slug})
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Convites de unidade")

    def test_cria_convite_com_link(self):
        resposta = self.client.post(
            reverse("convites", kwargs={"slug": self.condominio.slug}),
            {"unidade": self.unidade.pk, "papel": VinculoUnidade.Papel.MORADOR},
        )

        convite = Convite.objects.get()
        self.assertRedirects(
            resposta, reverse("convites", kwargs={"slug": self.condominio.slug})
        )
        self.assertEqual(convite.criado_por, self.sindico)
        self.assertTrue(convite.valido)

    def test_morador_nao_cria_convite(self):
        morador = Usuario.objects.create_user(
            username="morador", email="morador@example.com", password=SENHA
        )
        VinculoUnidade.objects.create(
            usuario=morador, unidade=self.unidade, papel=VinculoUnidade.Papel.MORADOR
        )
        self.client.force_login(morador)

        resposta = self.client.get(
            reverse("convites", kwargs={"slug": self.condominio.slug})
        )

        self.assertEqual(resposta.status_code, 403)


class ConvitePublicoTests(TestCase):
    def setUp(self):
        self.condominio, self.unidade = criar_base()
        self.convite = Convite.objects.create(
            condominio=self.condominio, unidade=self.unidade
        )

    def _url(self):
        return reverse(
            "usar_convite",
            kwargs={"slug": self.condominio.slug, "token": self.convite.token},
        )

    def test_pagina_mostra_unidade_do_convite(self):
        resposta = self.client.get(self._url())

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Convite válido")
        self.assertContains(resposta, self.unidade.rotulo)

    def test_cadastro_cria_usuario_vinculo_e_entra(self):
        resposta = self.client.post(
            self._url(),
            {
                "nome": "Ana Souza",
                "username": "ana",
                "email": "ana@example.com",
                "telefone": "",
                "senha": SENHA,
                "confirmar_senha": SENHA,
            },
        )

        usuario = Usuario.objects.get(username="ana")
        self.assertRedirects(
            resposta,
            reverse("agenda", kwargs={"slug": self.condominio.slug}),
            fetch_redirect_response=False,
        )
        self.assertEqual(usuario.first_name, "Ana Souza")
        self.assertTrue(
            VinculoUnidade.objects.filter(
                usuario=usuario, unidade=self.unidade, ativo=True
            ).exists()
        )
        self.convite.refresh_from_db()
        self.assertEqual(self.convite.usado_por, usuario)
        self.assertEqual(int(self.client.session["_auth_user_id"]), usuario.pk)

    def test_convite_usado_fica_invalido(self):
        self.convite.usado_em = timezone.now()
        self.convite.save(update_fields=["usado_em"])

        resposta = self.client.get(self._url())

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "não pode mais ser usado")

    def test_convite_expirado_fica_invalido(self):
        self.convite.expira_em = timezone.now() - timedelta(hours=1)
        self.convite.save(update_fields=["expira_em"])

        resposta = self.client.get(self._url())

        self.assertContains(resposta, "não pode mais ser usado")

    def test_usuario_logado_apenas_vincula_unidade(self):
        usuario = Usuario.objects.create_user(
            username="carlos", email="carlos@example.com", password=SENHA
        )
        self.client.force_login(usuario)

        resposta = self.client.get(self._url())

        self.assertRedirects(
            resposta,
            reverse("agenda", kwargs={"slug": self.condominio.slug}),
            fetch_redirect_response=False,
        )
        self.assertTrue(
            VinculoUnidade.objects.filter(
                usuario=usuario, unidade=self.unidade, ativo=True
            ).exists()
        )
        self.convite.refresh_from_db()
        self.assertEqual(self.convite.usado_por, usuario)


class LoginTests(TestCase):
    def test_pagina_de_login_renderiza(self):
        resposta = self.client.get(reverse("login"))

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Entrar na sua conta")

    def test_login_redireciona_para_agenda(self):
        condominio, unidade = criar_base()
        criar_sindico(unidade)
        destino = reverse("agenda", kwargs={"slug": condominio.slug})

        resposta = self.client.post(
            f"{reverse('login')}?next={destino}",
            {"username": "sindico", "password": SENHA},
        )

        self.assertRedirects(resposta, destino, fetch_redirect_response=False)

    def test_area_restrita_envia_para_login(self):
        condominio, _ = criar_base()

        resposta = self.client.get(
            reverse("minhas_reservas", kwargs={"slug": condominio.slug})
        )

        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("login"), resposta.url)
