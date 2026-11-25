import tempfile
from decimal import Decimal
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from apps.reservas.models import Local
from apps.usuarios.models import Unidade, Usuario, VinculoUnidade

from .models import Condominio

SENHA = "Senha-Forte-2026"


def criar_base():
    condominio = Condominio.objects.create(nome="Bela Vista", slug="bela-vista")
    unidade = Unidade.objects.create(condominio=condominio, bloco="A", numero="101")
    return condominio, unidade


def criar_usuario(username, unidade=None, papel=None):
    usuario = Usuario.objects.create_user(
        username=username, email=f"{username}@example.com", password=SENHA
    )
    if unidade is not None and papel is not None:
        VinculoUnidade.objects.create(usuario=usuario, unidade=unidade, papel=papel)
    return usuario


def imagem(nome="logo.png"):
    buffer = BytesIO()
    Image.new("RGB", (4, 4), "white").save(buffer, format="PNG")
    return SimpleUploadedFile(nome, buffer.getvalue(), content_type="image/png")


class PapeisTests(TestCase):
    def setUp(self):
        self.condominio, self.unidade = criar_base()

    def test_morador_nao_entra_na_gestao(self):
        morador = criar_usuario("morador", self.unidade, VinculoUnidade.Papel.MORADOR)
        self.client.force_login(morador)

        resposta = self.client.get(reverse("gestao", args=[self.condominio.slug]))

        self.assertEqual(resposta.status_code, 403)

    def test_administradora_entra_na_gestao_mas_nao_no_painel(self):
        gestora = criar_usuario(
            "gestora", self.unidade, VinculoUnidade.Papel.ADMINISTRADORA
        )
        self.client.force_login(gestora)

        self.assertEqual(
            self.client.get(reverse("gestao", args=[self.condominio.slug])).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("painel", args=[self.condominio.slug])).status_code,
            403,
        )

    def test_sindico_entra_no_painel(self):
        sindico = criar_usuario("sindico", self.unidade, VinculoUnidade.Papel.SINDICO)
        self.client.force_login(sindico)

        self.assertEqual(
            self.client.get(reverse("painel", args=[self.condominio.slug])).status_code,
            200,
        )

    def test_sindico_ajusta_quando_nao_ha_administradora(self):
        sindico = criar_usuario("sindico", self.unidade, VinculoUnidade.Papel.SINDICO)
        self.client.force_login(sindico)

        self.assertEqual(
            self.client.get(reverse("gestao", args=[self.condominio.slug])).status_code,
            200,
        )

    def test_sindico_ajusta_mesmo_com_administradora(self):
        sindico = criar_usuario("sindico", self.unidade, VinculoUnidade.Papel.SINDICO)
        criar_usuario("gestora", self.unidade, VinculoUnidade.Papel.ADMINISTRADORA)
        self.client.force_login(sindico)

        self.assertEqual(
            self.client.get(reverse("gestao", args=[self.condominio.slug])).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("painel", args=[self.condominio.slug])).status_code,
            200,
        )

    def test_agenda_mostra_painel_apenas_para_sindico(self):
        morador = criar_usuario("morador", self.unidade, VinculoUnidade.Papel.MORADOR)
        self.client.force_login(morador)
        html = self.client.get(
            reverse("agenda", args=[self.condominio.slug])
        ).content.decode()

        self.assertNotIn(">Painel<", html)
        self.assertIn(f"Olá, {morador.first_name or morador.username}", html)

    def test_agenda_do_morador_nao_expoe_area_administrativa(self):
        morador = criar_usuario("morador", self.unidade, VinculoUnidade.Papel.MORADOR)
        self.client.force_login(morador)
        html = self.client.get(
            reverse("agenda", args=[self.condominio.slug])
        ).content.decode()

        self.assertNotIn("Ambiente demo", html)
        self.assertNotIn("próxima fase", html)
        self.assertNotIn(f'href="{reverse("gestao", args=[self.condominio.slug])}"', html)
        self.assertNotIn(f'href="{reverse("painel", args=[self.condominio.slug])}"', html)
        self.assertIn(f'href="{reverse("minha_conta", args=[self.condominio.slug])}"', html)
        self.assertIn("Morador", html)

    def test_agenda_do_sindico_expoe_painel_e_gestao(self):
        sindico = criar_usuario("sindico", self.unidade, VinculoUnidade.Papel.SINDICO)
        self.client.force_login(sindico)
        html = self.client.get(
            reverse("agenda", args=[self.condominio.slug])
        ).content.decode()

        self.assertIn(f'href="{reverse("painel", args=[self.condominio.slug])}"', html)
        self.assertIn(f'href="{reverse("gestao", args=[self.condominio.slug])}"', html)
        self.assertIn("Síndico", html)
        self.assertNotIn("Ambiente demo", html)

    def test_agenda_da_administradora_nao_mostra_painel(self):
        gestora = criar_usuario(
            "gestora", self.unidade, VinculoUnidade.Papel.ADMINISTRADORA
        )
        self.client.force_login(gestora)
        html = self.client.get(
            reverse("agenda", args=[self.condominio.slug])
        ).content.decode()

        self.assertIn(f'href="{reverse("gestao", args=[self.condominio.slug])}"', html)
        self.assertNotIn(f'href="{reverse("painel", args=[self.condominio.slug])}"', html)
        self.assertIn("Administradora", html)


class MinhaContaTests(TestCase):
    def setUp(self):
        self.condominio, self.unidade = criar_base()

    def test_anonimo_e_enviado_para_o_login(self):
        resposta = self.client.get(
            reverse("minha_conta", args=[self.condominio.slug])
        )

        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("login"), resposta["Location"])

    def test_morador_ve_seus_dados_e_vinculos(self):
        morador = criar_usuario("morador", self.unidade, VinculoUnidade.Papel.MORADOR)
        self.client.force_login(morador)

        resposta = self.client.get(reverse("minha_conta", args=[self.condominio.slug]))

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, self.unidade.rotulo)
        self.assertContains(resposta, "Morador")
        self.assertNotContains(
            resposta, f'href="{reverse("gestao", args=[self.condominio.slug])}"'
        )

    def test_sindico_ve_atalhos_administrativos(self):
        sindico = criar_usuario("sindico", self.unidade, VinculoUnidade.Papel.SINDICO)
        self.client.force_login(sindico)

        resposta = self.client.get(reverse("minha_conta", args=[self.condominio.slug]))

        self.assertContains(
            resposta, f'href="{reverse("gestao", args=[self.condominio.slug])}"'
        )
        self.assertContains(
            resposta, f'href="{reverse("painel", args=[self.condominio.slug])}"'
        )

    def test_troca_de_senha(self):
        morador = criar_usuario("morador", self.unidade, VinculoUnidade.Papel.MORADOR)
        self.client.force_login(morador)

        resposta = self.client.post(
            reverse("trocar_senha", args=[self.condominio.slug]),
            {
                "old_password": SENHA,
                "new_password1": "Nova-Senha-Forte-2026",
                "new_password2": "Nova-Senha-Forte-2026",
            },
        )

        self.assertRedirects(
            resposta,
            reverse("minha_conta", args=[self.condominio.slug]),
            fetch_redirect_response=False,
        )
        morador.refresh_from_db()
        self.assertTrue(morador.check_password("Nova-Senha-Forte-2026"))


class LoginRedirectTests(TestCase):
    def test_login_leva_o_morador_para_a_agenda_do_condominio(self):
        condominio, unidade = criar_base()
        criar_usuario("morador", unidade, VinculoUnidade.Papel.MORADOR)

        resposta = self.client.post(
            reverse("login"), {"username": "morador", "password": SENHA}
        )

        self.assertRedirects(
            resposta,
            reverse("agenda", args=[condominio.slug]),
            fetch_redirect_response=False,
        )

    def test_login_respeita_o_next(self):
        condominio, unidade = criar_base()
        criar_usuario("morador", unidade, VinculoUnidade.Papel.MORADOR)

        resposta = self.client.post(
            reverse("login")
            + "?next="
            + reverse("minhas_reservas", args=[condominio.slug]),
            {"username": "morador", "password": SENHA},
        )

        self.assertRedirects(
            resposta,
            reverse("minhas_reservas", args=[condominio.slug]),
            fetch_redirect_response=False,
        )


class LocaisTests(TestCase):
    def setUp(self):
        self.condominio, self.unidade = criar_base()
        self.gestora = criar_usuario(
            "gestora", self.unidade, VinculoUnidade.Papel.ADMINISTRADORA
        )
        self.client.force_login(self.gestora)
        self.diretorio = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.diretorio)
        self.override.enable()

    def tearDown(self):
        self.override.disable()

    def test_cria_espaco_com_valor_e_foto(self):
        resposta = self.client.post(
            reverse("locais", args=[self.condominio.slug]),
            {
                "nome": "Salão de Festas",
                "categoria": Local.Categoria.SALAO,
                "descricao": "Com cozinha",
                "capacidade": "80",
                "valor": "350.00",
                "foto": imagem(),
                "ordem": "1",
                "ativo": "on",
            },
        )

        self.assertEqual(resposta.status_code, 302)
        local = Local.all_objects.get(condominio=self.condominio, nome="Salão de Festas")
        self.assertEqual(local.valor, Decimal("350.00"))
        self.assertEqual(local.slug, "salao-de-festas")
        self.assertTrue(local.foto)

    def test_edita_valor_do_espaco(self):
        local = Local.objects.create(
            condominio=self.condominio, nome="Quiosque", slug="quiosque"
        )

        self.client.post(
            reverse("local_editar", args=[self.condominio.slug, local.pk]),
            {
                "nome": "Quiosque",
                "categoria": Local.Categoria.QUIOSQUE,
                "valor": "199.90",
                "capacidade": "0",
                "ordem": "0",
                "ativo": "on",
            },
        )

        local.refresh_from_db()
        self.assertEqual(local.valor, Decimal("199.90"))

    def test_alterna_disponibilidade(self):
        local = Local.objects.create(
            condominio=self.condominio, nome="Quadra", slug="quadra"
        )

        self.client.post(
            reverse("local_alternar", args=[self.condominio.slug, local.pk])
        )

        local.refresh_from_db()
        self.assertFalse(local.ativo)


class UnidadesTests(TestCase):
    def setUp(self):
        self.condominio, self.unidade = criar_base()
        gestora = criar_usuario(
            "gestora", self.unidade, VinculoUnidade.Papel.ADMINISTRADORA
        )
        self.client.force_login(gestora)

    def test_cria_unidade(self):
        self.client.post(
            reverse("unidades", args=[self.condominio.slug]),
            {"bloco": "B", "numero": "202"},
        )

        self.assertTrue(
            self.condominio.unidades.filter(bloco="B", numero="202").exists()
        )

    def test_bloqueia_unidade_repetida(self):
        resposta = self.client.post(
            reverse("unidades", args=[self.condominio.slug]),
            {"bloco": "A", "numero": "101"},
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(self.condominio.unidades.count(), 1)


class IdentidadeTests(TestCase):
    def setUp(self):
        self.condominio, self.unidade = criar_base()
        gestora = criar_usuario(
            "gestora", self.unidade, VinculoUnidade.Papel.ADMINISTRADORA
        )
        self.client.force_login(gestora)
        self.override = override_settings(MEDIA_ROOT=tempfile.mkdtemp())
        self.override.enable()

    def tearDown(self):
        self.override.disable()

    def test_envia_logo_e_renomeia(self):
        resposta = self.client.post(
            reverse("identidade", args=[self.condominio.slug]),
            {"nome": "Bela Vista Residence", "logo": imagem()},
        )

        self.assertEqual(resposta.status_code, 302)
        self.condominio.refresh_from_db()
        self.assertEqual(self.condominio.nome, "Bela Vista Residence")
        self.assertTrue(self.condominio.logo)

    def test_pagina_tem_botao_de_upload(self):
        resposta = self.client.get(
            reverse("identidade", args=[self.condominio.slug])
        )

        self.assertContains(resposta, "Escolher imagem")

    def test_quantidade_declarada_alimenta_a_gestao(self):
        resposta = self.client.post(
            reverse("identidade", args=[self.condominio.slug]),
            {"nome": "Bela Vista", "quantidade_unidades": 48},
        )

        self.assertEqual(resposta.status_code, 302)
        self.condominio.refresh_from_db()
        self.assertEqual(self.condominio.quantidade_unidades, 48)
        self.assertContains(
            self.client.get(reverse("gestao", args=[self.condominio.slug])), "48"
        )


class PlataformaTests(TestCase):
    def setUp(self):
        self.condominio, self.unidade = criar_base()
        self.dono = Usuario.objects.create_superuser(
            username="dono", email="dono@example.com", password=SENHA
        )

    def test_morador_nao_entra_na_plataforma(self):
        morador = criar_usuario("morador", self.unidade, VinculoUnidade.Papel.MORADOR)

        resposta = self.client.post(
            reverse("plataforma_entrar"),
            {"username": "morador", "password": SENHA},
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(morador.username, "morador")

    def test_dono_entra_e_cria_condominio(self):
        resposta = self.client.post(
            reverse("plataforma_entrar"),
            {"username": "dono", "password": SENHA},
        )
        self.assertRedirects(resposta, reverse("plataforma"))

        resposta = self.client.post(
            reverse("plataforma"), {"nome": "Jardim Azul", "slug": "jardim-azul"}
        )

        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(Condominio.objects.filter(slug="jardim-azul").exists())

    def test_quantidade_declarada_sugere_plano_maior(self):
        self.client.force_login(self.dono)
        self.condominio.quantidade_unidades = 60
        self.condominio.save()

        resposta = self.client.get(reverse("plataforma"))

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.context["condominios"][0].plano_sugerido.slug, "pro")

    def test_painel_da_plataforma_exige_superuser(self):
        morador = criar_usuario("morador", self.unidade, VinculoUnidade.Papel.MORADOR)
        self.client.force_login(morador)

        resposta = self.client.get(reverse("plataforma"))

        self.assertRedirects(resposta, reverse("plataforma_entrar"))

    def test_armazenamento_mostra_backend_ativo(self):
        self.client.force_login(self.dono)

        resposta = self.client.get(reverse("plataforma_armazenamento"))

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "FileSystemStorage")

    def test_armazenamento_sem_arquivo_mostra_erro(self):
        self.client.force_login(self.dono)

        resposta = self.client.post(reverse("plataforma_armazenamento"), {})

        self.assertContains(resposta, "Escolha um arquivo")

    def test_armazenamento_exige_superuser(self):
        morador = criar_usuario("morador", self.unidade, VinculoUnidade.Papel.MORADOR)
        self.client.force_login(morador)

        resposta = self.client.get(reverse("plataforma_armazenamento"))

        self.assertRedirects(resposta, reverse("plataforma_entrar"))


class BloqueioDeReservasTests(TestCase):
    def setUp(self):
        self.condominio, self.unidade = criar_base()
        self.sindico = criar_usuario(
            "sindico", self.unidade, VinculoUnidade.Papel.SINDICO
        )
        self.morador = criar_usuario(
            "morador", self.unidade, VinculoUnidade.Papel.MORADOR
        )
        self.vinculo = VinculoUnidade.objects.get(
            usuario=self.morador, unidade=self.unidade
        )
        self.url = reverse(
            "vinculo_alternar_bloqueio", args=[self.condominio.slug, self.vinculo.pk]
        )

    def test_sindico_bloqueia_e_desbloqueia(self):
        self.client.force_login(self.sindico)

        resposta = self.client.post(self.url)

        self.assertRedirects(
            resposta,
            reverse("unidade_editar", args=[self.condominio.slug, self.unidade.pk]),
        )
        self.vinculo.refresh_from_db()
        self.assertTrue(self.vinculo.bloqueio_reservas)

        self.client.post(self.url)
        self.vinculo.refresh_from_db()
        self.assertFalse(self.vinculo.bloqueio_reservas)

    def test_morador_nao_pode_alternar_bloqueio(self):
        self.client.force_login(self.morador)

        resposta = self.client.post(self.url)

        self.assertEqual(resposta.status_code, 403)
        self.vinculo.refresh_from_db()
        self.assertFalse(self.vinculo.bloqueio_reservas)

    def test_editar_unidade_mostra_botao_de_bloquear(self):
        self.client.force_login(self.sindico)

        resposta = self.client.get(
            reverse("unidade_editar", args=[self.condominio.slug, self.unidade.pk])
        )

        self.assertContains(resposta, "Bloquear reservas")
        self.assertContains(resposta, self.url)
