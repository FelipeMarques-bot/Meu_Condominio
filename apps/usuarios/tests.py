import re
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

        pagina = self.client.get(
            reverse("convites", kwargs={"slug": self.condominio.slug})
        )
        self.assertContains(pagina, "Enviar por WhatsApp")
        self.assertContains(pagina, "data-wa-desktop")
        self.assertContains(pagina, "app_absent=1")

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
                "telefone": "(47) 99999-0000",
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
        self.assertEqual(usuario.telefone, "(47) 99999-0000")
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

    def test_usuario_logado_confirma_antes_de_vincular(self):
        usuario = Usuario.objects.create_user(
            username="carlos", email="carlos@example.com", password=SENHA
        )
        usuario.telefone = "(47) 98888-7777"
        usuario.save(update_fields=["telefone"])
        self.client.force_login(usuario)

        resposta = self.client.get(self._url())

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Sou eu, vincular esta unidade")
        self.assertFalse(
            VinculoUnidade.objects.filter(usuario=usuario).exists()
        )

        resposta = self.client.post(self._url(), {"acao": "usar"})

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

    def test_usuario_sem_telefone_precisa_informar_antes(self):
        usuario = Usuario.objects.create_user(
            username="carlos", email="carlos@example.com", password=SENHA
        )
        self.client.force_login(usuario)

        resposta = self.client.get(self._url())
        self.assertContains(resposta, "Falta o celular na sua conta")

        resposta = self.client.post(self._url(), {"acao": "usar"})
        self.assertContains(resposta, "Este campo é obrigatório")
        self.assertFalse(
            VinculoUnidade.objects.filter(usuario=usuario).exists()
        )

        resposta = self.client.post(
            self._url(),
            {"acao": "usar", "telefone": "(47) 98888-7777"},
        )
        self.assertRedirects(
            resposta,
            reverse("agenda", kwargs={"slug": self.condominio.slug}),
            fetch_redirect_response=False,
        )
        usuario.refresh_from_db()
        self.assertEqual(usuario.telefone, "(47) 98888-7777")
        self.assertTrue(
            VinculoUnidade.objects.filter(
                usuario=usuario, unidade=self.unidade, ativo=True
            ).exists()
        )

    def test_sair_do_convite_encerra_a_sessao(self):
        usuario = Usuario.objects.create_user(
            username="carlos", email="carlos@example.com", password=SENHA
        )
        usuario.telefone = "(47) 98888-7777"
        usuario.save(update_fields=["telefone"])
        self.client.force_login(usuario)

        resposta = self.client.post(self._url(), {"acao": "sair"})

        self.assertRedirects(resposta, self._url(), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)


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


class VinculoRemoverTests(TestCase):
    def test_sindico_remove_vinculo_da_unidade(self):
        condominio, unidade = criar_base()
        sindico = criar_sindico(unidade)
        morador = Usuario.objects.create_user(
            username="morador", email="morador@example.com", password=SENHA
        )
        vinculo = VinculoUnidade.objects.create(
            usuario=morador, unidade=unidade, papel=VinculoUnidade.Papel.MORADOR
        )
        self.client.force_login(sindico)

        resposta = self.client.post(
            reverse(
                "vinculo_remover",
                kwargs={"slug": condominio.slug, "pk": vinculo.pk},
            )
        )

        self.assertRedirects(
            resposta,
            reverse(
                "unidade_editar",
                kwargs={"slug": condominio.slug, "pk": unidade.pk},
            ),
        )
        self.assertFalse(VinculoUnidade.objects.filter(pk=vinculo.pk).exists())


class PlataformaAcessoTests(TestCase):
    def test_visitante_nao_abre_armazenamento(self):
        resposta = self.client.get(reverse("plataforma_armazenamento"))

        self.assertRedirects(
            resposta, reverse("plataforma_entrar"), fetch_redirect_response=False
        )

    def test_morador_nao_abre_armazenamento(self):
        condominio, unidade = criar_base()
        morador = Usuario.objects.create_user(
            username="morador", email="morador@example.com", password=SENHA
        )
        VinculoUnidade.objects.create(usuario=morador, unidade=unidade)
        self.client.force_login(morador)

        resposta = self.client.get(reverse("plataforma_armazenamento"))

        self.assertRedirects(
            resposta, reverse("plataforma_entrar"), fetch_redirect_response=False
        )


class ConviteExcluirTests(TestCase):
    def test_sindico_exclui_convite(self):
        condominio, unidade = criar_base()
        sindico = criar_sindico(unidade)
        convite = Convite.objects.create(condominio=condominio, unidade=unidade)
        self.client.force_login(sindico)

        resposta = self.client.post(
            reverse(
                "convite_excluir",
                kwargs={"slug": condominio.slug, "pk": convite.pk},
            )
        )

        self.assertRedirects(
            resposta,
            reverse("convites", kwargs={"slug": condominio.slug}),
        )
        self.assertFalse(Convite.objects.filter(pk=convite.pk).exists())

    def test_excluir_convite_usado_remove_vinculo_do_morador(self):
        condominio, unidade = criar_base()
        sindico = criar_sindico(unidade)
        morador = Usuario.objects.create_user(
            username="morador", email="morador@example.com", password=SENHA
        )
        vinculo = VinculoUnidade.objects.create(usuario=morador, unidade=unidade)
        convite = Convite.objects.create(
            condominio=condominio,
            unidade=unidade,
            usado_em=timezone.now(),
            usado_por=morador,
        )
        self.client.force_login(sindico)

        self.client.post(
            reverse(
                "convite_excluir",
                kwargs={"slug": condominio.slug, "pk": convite.pk},
            )
        )

        self.assertFalse(VinculoUnidade.objects.filter(pk=vinculo.pk).exists())
        self.assertTrue(Usuario.objects.filter(pk=morador.pk).exists())


class RedefinirSenhaTests(TestCase):
    def test_sindico_gera_senha_temporaria(self):
        condominio, unidade = criar_base()
        sindico = criar_sindico(unidade)
        morador = Usuario.objects.create_user(
            username="morador", email="morador@example.com", password=SENHA
        )
        vinculo = VinculoUnidade.objects.create(usuario=morador, unidade=unidade)
        self.client.force_login(sindico)

        resposta = self.client.post(
            reverse(
                "vinculo_redefinir_senha",
                kwargs={"slug": condominio.slug, "pk": vinculo.pk},
            )
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Senha temporária")
        encontrada = re.search(rb">([A-Za-z2-9]{10})</code>", resposta.content)
        self.assertIsNotNone(encontrada)
        morador.refresh_from_db()
        self.assertTrue(morador.check_password(encontrada.group(1).decode()))


class MeusCondominiosTests(TestCase):
    def test_sindico_ve_o_condominio_na_lista(self):
        condominio, unidade = criar_base()
        sindico = criar_sindico(unidade)
        self.client.force_login(sindico)

        resposta = self.client.get(reverse("meus_condominios"))

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, condominio.nome)
        self.assertContains(resposta, "Gerenciar")

    def test_login_do_sindico_vai_para_a_gestao(self):
        condominio, unidade = criar_base()
        sindico = criar_sindico(unidade)

        resposta = self.client.post(
            reverse("login"),
            {"username": sindico.username, "password": SENHA},
        )

        self.assertRedirects(
            resposta,
            reverse("gestao", kwargs={"slug": condominio.slug}),
            fetch_redirect_response=False,
        )
