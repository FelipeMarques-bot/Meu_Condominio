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
        "bloco": "A",
        "numero": "101",
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
        self.assertEqual((unidade.bloco, unidade.numero), ("A", "101"))

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
            dados(username="ana2", email="ana2@example.com"),
        )

        slugs = set(Condominio.objects.values_list("slug", flat=True))
        self.assertEqual(slugs, {"jardim-das-flores", "jardim-das-flores-2"})

    def test_slug_em_uso_bloqueia(self):
        Condominio.objects.create(nome="Existente", slug="jardim-das-flores")

        resposta = self.client.post(reverse("criar_condominio"), dados(slug="jardim-das-flores"))

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "já está em uso")
        self.assertEqual(Condominio.objects.count(), 1)
        self.assertFalse(Usuario.objects.filter(username="ana").exists())

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

    def test_usuario_autenticado_vai_para_a_gestao(self):
        condominio = Condominio.objects.create(nome="Bela Vista", slug="bela-vista")
        unidade = Unidade.objects.create(condominio=condominio, numero="101")
        sindico = Usuario.objects.create_user(username="sindico", password=SENHA)
        VinculoUnidade.objects.create(
            usuario=sindico, unidade=unidade, papel=VinculoUnidade.Papel.SINDICO
        )
        self.client.force_login(sindico)

        resposta = self.client.get(reverse("criar_condominio"))

        self.assertRedirects(
            resposta, reverse("gestao", args=["bela-vista"]), fetch_redirect_response=False
        )

    def test_trial_de_14_dias(self):
        self.client.post(reverse("criar_condominio"), dados())

        condominio = Condominio.objects.get()
        self.assertIsNotNone(condominio.trial_ate)
        self.assertLessEqual(condominio.trial_ate - timezone.now(), timedelta(days=14))
