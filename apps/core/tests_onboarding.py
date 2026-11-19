from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.usuarios.models import Unidade, Usuario, VinculoUnidade

from .models import Condominio, ConfiguracaoCondominio

SENHA = "Senha-Forte-2026"


def dados(**extras):
    base = {
        "condominio": "Jardim das Flores",
        "nome": "Ana Souza",
        "username": "ana",
        "email": "ana@example.com",
        "telefone": "(47) 99999-0000",
        "senha": SENHA,
        "confirmar_senha": SENHA,
    }
    base.update(extras)
    return base


class OnboardingTests(TestCase):
    def test_pagina_abre(self):
        resposta = self.client.get(reverse("criar_condominio"))

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Criar meu condomínio")

    def test_cria_condominio_unidade_e_sindico(self):
        resposta = self.client.post(reverse("criar_condominio"), dados())

        condominio = Condominio.objects.get()
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(
            resposta["Location"], reverse("gestao", args=[condominio.slug])
        )
        self.assertEqual(condominio.slug, "jardim-das-flores")
        self.assertEqual(condominio.plano.slug, "essencial")
        self.assertTrue(condominio.em_trial)
        self.assertGreaterEqual(condominio.dias_de_trial, 13)
        self.assertTrue(ConfiguracaoCondominio.objects.filter(condominio=condominio).exists())

        unidade = Unidade.objects.get(condominio=condominio)
        self.assertEqual(unidade.numero, "Administração")
        self.assertTrue(unidade.administrativa)

        usuario = Usuario.objects.get(username="ana")
        self.assertEqual(usuario.first_name, "Ana Souza")
        self.assertEqual(usuario.telefone, "(47) 99999-0000")
        self.assertTrue(
            VinculoUnidade.objects.filter(
                usuario=usuario,
                unidade=unidade,
                papel=VinculoUnidade.Papel.SINDICO,
                ativo=True,
            ).exists()
        )

        self.assertEqual(int(self.client.session["_auth_user_id"]), usuario.pk)
        self.assertEqual(
            self.client.get(reverse("gestao", args=[condominio.slug])).status_code, 200
        )

    def test_slug_em_branco_vira_slug_do_nome(self):
        self.client.post(reverse("criar_condominio"), dados(nome="Carlos Lima", username="carlos"))

        self.assertEqual(Condominio.objects.get().slug, "jardim-das-flores")

    def test_nomes_iguais_geram_slugs_diferentes(self):
        self.client.post(reverse("criar_condominio"), dados())
        self.client.logout()
        self.client.post(
            reverse("criar_condominio"),
            dados(
                username="ana2",
                email="ana2@example.com",
                telefone="(47) 98888-1111",
            ),
            REMOTE_ADDR="198.51.100.7",
        )

        slugs = set(Condominio.objects.values_list("slug", flat=True))
        self.assertEqual(slugs, {"jardim-das-flores", "jardim-das-flores-2"})

    def test_slug_em_uso_ganha_sufixo(self):
        Condominio.objects.create(nome="Existente", slug="jardim-das-flores")

        resposta = self.client.post(
            reverse("criar_condominio"), dados(slug="jardim-das-flores")
        )

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(
            Condominio.objects.get(nome="Jardim das Flores").slug,
            "jardim-das-flores-2",
        )

    def test_slug_aceito_por_extenso(self):
        self.client.post(
            reverse("criar_condominio"), dados(slug="Condomínio Bela Vista, 123")
        )

        self.assertEqual(
            Condominio.objects.get().slug, "condominio-bela-vista-123"
        )

    def test_senha_divergente_nao_cria_nada(self):
        resposta = self.client.post(
            reverse("criar_condominio"), dados(confirmar_senha="Outra-Senha-2026")
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(Condominio.objects.exists())
        self.assertFalse(Usuario.objects.filter(username="ana").exists())

    def test_email_repetido_bloqueia(self):
        Usuario.objects.create_user(
            username="outra", email="ana@example.com", password=SENHA
        )

        resposta = self.client.post(reverse("criar_condominio"), dados())

        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(Condominio.objects.exists())

    def test_usuario_logado_ve_formulario_de_novo_condominio(self):
        condominio = Condominio.objects.create(nome="Bela Vista", slug="bela-vista")
        unidade = Unidade.objects.create(condominio=condominio, numero="101")
        morador = Usuario.objects.create_user(username="morador", password=SENHA)
        VinculoUnidade.objects.create(
            usuario=morador, unidade=unidade, papel=VinculoUnidade.Papel.MORADOR
        )
        self.client.force_login(morador)

        resposta = self.client.get(reverse("criar_condominio"))

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Criar outro condomínio")
        self.assertContains(resposta, 'name="slug"')
        self.assertNotContains(resposta, 'name="numero"')

    def test_usuario_logado_cria_outro_condominio_sem_trocar_de_conta(self):
        antigo = Condominio.objects.create(nome="Bela Vista", slug="bela-vista")
        unidade = Unidade.objects.create(condominio=antigo, numero="101")
        morador = Usuario.objects.create_user(username="morador", password=SENHA)
        VinculoUnidade.objects.create(
            usuario=morador, unidade=unidade, papel=VinculoUnidade.Papel.MORADOR
        )
        self.client.force_login(morador)

        resposta = self.client.post(
            reverse("criar_condominio"),
            {
                "nome": "Jardim das Flores",
                "slug": "jardim-das-flores",
            },
        )

        novo = Condominio.objects.get(slug="jardim-das-flores")
        self.assertRedirects(
            resposta,
            reverse("gestao", args=[novo.slug]),
            fetch_redirect_response=False,
        )
        self.assertTrue(
            VinculoUnidade.objects.filter(
                usuario=morador,
                unidade__condominio=novo,
                papel=VinculoUnidade.Papel.SINDICO,
                ativo=True,
            ).exists()
        )
        self.assertTrue(Usuario.objects.filter(pk=morador.pk).exists())

    def test_usuario_logado_com_slug_existente_recebe_sufixo(self):
        Condominio.objects.create(nome="Bela Vista", slug="bela-vista")
        usuario = Usuario.objects.create_user(username="sindico", password=SENHA)
        self.client.force_login(usuario)

        resposta = self.client.post(
            reverse("criar_condominio"),
            {"nome": "Outro", "slug": "bela-vista"},
        )

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(Condominio.objects.count(), 2)
        self.assertTrue(Condominio.objects.filter(slug="bela-vista-2").exists())

    def test_trial_de_14_dias(self):
        self.client.post(reverse("criar_condominio"), dados())

        condominio = Condominio.objects.get()
        self.assertIsNotNone(condominio.trial_ate)
        self.assertLessEqual(condominio.trial_ate - timezone.now(), timedelta(days=14))
