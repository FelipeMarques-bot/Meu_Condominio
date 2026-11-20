from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.reservas.models import Local
from apps.usuarios.models import Convite, Unidade, Usuario, VinculoUnidade

from .models import Condominio, PagamentoPlano, Plano
from .trial import hash_ip

SENHA = "Senha-Forte-2026"


def criar_base(
    trial_ate=None,
    assinatura_valida_ate=None,
    isento=False,
    vencimento_em=None,
    dia_vencimento=None,
):
    condominio = Condominio.objects.create(
        nome="Bela Vista",
        slug="bela-vista",
        trial_ate=trial_ate,
        assinatura_valida_ate=assinatura_valida_ate,
        isento_assinatura=isento,
        vencimento_em=vencimento_em,
        dia_vencimento=dia_vencimento,
    )
    Local.objects.create(
        condominio=condominio, nome="Quiosque", slug="quiosque", valor="180.00"
    )
    unidade = Unidade.objects.create(
        condominio=condominio, numero="Administração", administrativa=True
    )
    sindico = Usuario.objects.create_user(
        username="sindico", email="sindico@example.com", password=SENHA
    )
    VinculoUnidade.objects.create(
        usuario=sindico,
        unidade=unidade,
        papel=VinculoUnidade.Papel.SINDICO,
    )
    return condominio, unidade, sindico


class AcessoPorAssinaturaTests(TestCase):
    def test_trial_ativo_libera_agenda_e_mostra_aviso(self):
        condominio, _, sindico = criar_base(
            trial_ate=timezone.now() + timedelta(days=5)
        )
        self.client.force_login(sindico)

        resposta = self.client.get(reverse("agenda", args=[condominio.slug]))

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "restantes")
        self.assertContains(resposta, "Ativar meu plano")

    def test_trial_expirado_bloqueia_agenda(self):
        condominio, _, sindico = criar_base(
            trial_ate=timezone.now() - timedelta(hours=1)
        )
        self.client.force_login(sindico)

        resposta = self.client.get(reverse("agenda", args=[condominio.slug]))

        self.assertRedirects(
            resposta,
            reverse("assinatura", args=[condominio.slug]),
            fetch_redirect_response=False,
        )
        bloqueada = self.client.get(reverse("assinatura", args=[condominio.slug]))
        self.assertEqual(bloqueada.status_code, 200)
        self.assertContains(bloqueada, "Acesso suspenso")

    def test_trial_expirado_ainda_permite_conta_e_senha(self):
        condominio, _, sindico = criar_base(
            trial_ate=timezone.now() - timedelta(hours=1)
        )
        self.client.force_login(sindico)

        resposta = self.client.get(reverse("minha_conta", args=[condominio.slug]))

        self.assertEqual(resposta.status_code, 200)

    def test_plano_pago_libera_acesso(self):
        condominio, _, sindico = criar_base(
            assinatura_valida_ate=timezone.now() + timedelta(days=20)
        )
        self.client.force_login(sindico)

        resposta = self.client.get(reverse("agenda", args=[condominio.slug]))

        self.assertEqual(resposta.status_code, 200)
        status = self.client.get(reverse("assinatura", args=[condominio.slug]))
        self.assertContains(status, "Plano ativo")

    def test_convite_fica_suspenso_com_trial_expirado(self):
        condominio, unidade, _ = criar_base(
            trial_ate=timezone.now() - timedelta(hours=1)
        )
        convite = Convite.objects.create(condominio=condominio, unidade=unidade)

        resposta = self.client.get(
            reverse(
                "usar_convite",
                kwargs={"slug": condominio.slug, "token": convite.token},
            )
        )

        self.assertEqual(resposta.status_code, 403)
        self.assertContains(resposta, "suspensos", status_code=403)


class PagamentoPlanoTests(TestCase):
    def setUp(self):
        self.condominio, self.unidade, self.sindico = criar_base(
            trial_ate=timezone.now() - timedelta(hours=1)
        )
        self.plano = Plano.objects.get(slug="conforto")
        self.client.force_login(self.sindico)

    def _comprovante(self):
        return SimpleUploadedFile(
            "pix.png",
            b"\x89PNG\r\n\x1a\nconteudo",
            content_type="image/png",
        )

    def test_sindico_envia_comprovante(self):
        resposta = self.client.post(
            reverse("assinatura", args=[self.condominio.slug]),
            {
                "plano": self.plano.pk,
                "dia_vencimento": 10,
                "comprovante": self._comprovante(),
            },
        )

        self.assertRedirects(
            resposta,
            reverse("assinatura", args=[self.condominio.slug]),
        )
        pagamento = PagamentoPlano.objects.get()
        self.assertEqual(pagamento.condominio, self.condominio)
        self.assertEqual(pagamento.plano, self.plano)
        self.assertEqual(pagamento.valor, self.plano.preco_mensal)
        self.assertEqual(pagamento.status, PagamentoPlano.Status.PENDENTE)

    def test_nao_aceita_dois_comprovantes_pendentes(self):
        PagamentoPlano.objects.create(
            condominio=self.condominio,
            plano=self.plano,
            valor=self.plano.preco_mensal,
            comprovante=self._comprovante(),
        )

        self.client.post(
            reverse("assinatura", args=[self.condominio.slug]),
            {
                "plano": self.plano.pk,
                "dia_vencimento": 10,
                "comprovante": self._comprovante(),
            },
        )

        self.assertEqual(PagamentoPlano.objects.count(), 1)

    def test_dono_confirma_e_libera_por_30_dias(self):
        pagamento = PagamentoPlano.objects.create(
            condominio=self.condominio,
            plano=self.plano,
            valor=self.plano.preco_mensal,
            dia_vencimento=10,
            comprovante=self._comprovante(),
        )
        dono = Usuario.objects.create_superuser(
            username="dono", email="dono@example.com", password=SENHA
        )
        self.client.force_login(dono)

        resposta = self.client.post(
            reverse("plataforma_pagamento_confirmar", args=[pagamento.pk]),
            {"acao": "confirmar", "observacao": "Pix conferido"},
        )

        self.assertRedirects(resposta, reverse("plataforma"))
        pagamento.refresh_from_db()
        self.condominio.refresh_from_db()
        self.assertEqual(pagamento.status, PagamentoPlano.Status.CONFIRMADO)
        self.assertEqual(pagamento.analisado_por, dono)
        self.assertEqual(self.condominio.plano, self.plano)
        self.assertEqual(self.condominio.dia_vencimento, 10)
        self.assertGreater(
            self.condominio.vencimento_em,
            timezone.localdate(),
        )
        self.assertEqual(self.condominio.vencimento_em.day, 10)
        self.assertGreaterEqual(
            self.condominio.dias_de_assinatura,
            5,
        )

        self.client.force_login(self.sindico)
        self.assertEqual(
            self.client.get(
                reverse("agenda", args=[self.condominio.slug])
            ).status_code,
            200,
        )

    def test_recusar_nao_libera(self):
        pagamento = PagamentoPlano.objects.create(
            condominio=self.condominio,
            plano=self.plano,
            valor=self.plano.preco_mensal,
            comprovante=self._comprovante(),
        )
        dono = Usuario.objects.create_superuser(
            username="dono", email="dono@example.com", password=SENHA
        )
        self.client.force_login(dono)

        self.client.post(
            reverse("plataforma_pagamento_confirmar", args=[pagamento.pk]),
            {"acao": "recusar"},
        )

        pagamento.refresh_from_db()
        self.condominio.refresh_from_db()
        self.assertEqual(pagamento.status, PagamentoPlano.Status.RECUSADO)
        self.assertIsNone(self.condominio.assinatura_valida_ate)


class LiberacaoManualTests(TestCase):
    def test_dono_libera_30_dias_sem_comprovante(self):
        condominio, _, sindico = criar_base(
            trial_ate=timezone.now() - timedelta(hours=1)
        )
        dono = Usuario.objects.create_superuser(
            username="dono", email="dono@example.com", password=SENHA
        )
        self.client.force_login(dono)

        resposta = self.client.post(
            reverse("plataforma_liberar", args=[condominio.pk])
        )

        self.assertRedirects(resposta, reverse("plataforma"))
        condominio.refresh_from_db()
        self.assertFalse(condominio.isento_assinatura)
        self.assertGreater(
            condominio.vencimento_em,
            timezone.localdate(),
        )
        self.client.force_login(sindico)
        self.assertEqual(
            self.client.get(reverse("agenda", args=[condominio.slug])).status_code,
            200,
        )


class TrialAbusoTests(TestCase):
    def test_bloqueia_novo_trial_do_mesmo_ip(self):
        Condominio.objects.create(
            nome="Antigo",
            slug="antigo",
            trial_ate=timezone.now() - timedelta(days=1),
            trial_ip_hash=hash_ip("203.0.113.9"),
        )

        resposta = self.client.post(
            reverse("criar_condominio"),
            {
                "condominio": "Jardim das Flores",
                "nome": "Ana Souza",
                "username": "ana",
                "email": "ana@example.com",
                "telefone": "(47) 99999-0000",
                "senha": SENHA,
                "confirmar_senha": SENHA,
            },
            REMOTE_ADDR="203.0.113.9",
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(Condominio.objects.count(), 1)
        self.assertContains(resposta, "Já existe um teste gratuito")


class CarenciaTests(TestCase):
    def test_trial_vencido_ainda_libera_na_carencia(self):
        condominio, _, sindico = criar_base(
            trial_ate=timezone.now() - timedelta(days=1),
            vencimento_em=timezone.localdate() - timedelta(days=1),
        )
        self.client.force_login(sindico)

        resposta = self.client.get(reverse("agenda", args=[condominio.slug]))

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "atraso h")
        self.assertContains(resposta, "1 dia")

    def test_bloqueia_depois_de_cinco_dias_de_carencia(self):
        condominio, _, sindico = criar_base(
            trial_ate=timezone.now() - timedelta(days=7),
            vencimento_em=timezone.localdate() - timedelta(days=6),
        )
        self.client.force_login(sindico)

        resposta = self.client.get(reverse("agenda", args=[condominio.slug]))

        self.assertRedirects(
            resposta,
            reverse("assinatura", args=[condominio.slug]),
            fetch_redirect_response=False,
        )

    def test_ultimo_dia_de_carencia_avisa_bloqueio(self):
        condominio, _, sindico = criar_base(
            trial_ate=timezone.now() - timedelta(days=6),
            vencimento_em=timezone.localdate() - timedelta(days=5),
        )
        self.client.force_login(sindico)

        resposta = self.client.get(reverse("agenda", args=[condominio.slug]))

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "ltimo dia")

    def test_vencimento_hoje_mostra_aviso(self):
        condominio, _, sindico = criar_base(
            trial_ate=timezone.now() - timedelta(days=1),
            vencimento_em=timezone.localdate(),
        )
        self.client.force_login(sindico)

        resposta = self.client.get(reverse("agenda", args=[condominio.slug]))

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "vence hoje")

    def test_pagamento_antecipado_mantem_o_dia_escolhido(self):
        condominio, _, _ = criar_base(
            vencimento_em=timezone.localdate() + timedelta(days=10),
            dia_vencimento=10,
        )
        antigo = condominio.vencimento_em
        pagamento = PagamentoPlano.objects.create(
            condominio=condominio,
            plano=Plano.objects.get(slug="conforto"),
            comprovante=SimpleUploadedFile(
                "pix.png",
                b"\x89PNG\r\n\x1a\nok",
                content_type="image/png",
            ),
            dia_vencimento=10,
        )
        dono = Usuario.objects.create_superuser(
            username="dono2", email="dono2@example.com", password=SENHA
        )
        self.client.force_login(dono)

        self.client.post(
            reverse("plataforma_pagamento_confirmar", args=[pagamento.pk]),
            {"acao": "confirmar"},
        )

        condominio.refresh_from_db()
        self.assertEqual(condominio.dia_vencimento, 10)
        self.assertEqual(condominio.vencimento_em.day, 10)
        self.assertGreater(condominio.vencimento_em, antigo)
