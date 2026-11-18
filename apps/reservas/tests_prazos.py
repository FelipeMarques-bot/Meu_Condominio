from datetime import datetime, time, timedelta

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.models import ConfiguracaoCondominio

from .models import Reserva
from .prazos import processar_prazos
from .tests import criar_base, criar_morador, criar_reserva, criar_sindico

BACKEND_EMAIL = "django.core.mail.backends.locmem.EmailBackend"


@override_settings(EMAIL_BACKEND=BACKEND_EMAIL)
class AvisosDeReservaTests(TestCase):
    def setUp(self):
        self.condominio, self.local, self.unidade = criar_base()
        self.morador = criar_morador(self.unidade)
        self.sindico = criar_sindico(self.condominio, self.unidade)

    def test_criacao_avisa_morador_e_administracao(self):
        self.client.force_login(self.morador)
        alvo = timezone.localtime(timezone.now()) + timedelta(days=3)

        self.client.post(
            reverse(
                "reservar",
                kwargs={"slug": self.condominio.slug, "local_slug": self.local.slug},
            ),
            {
                "data": alvo.strftime("%Y-%m-%d"),
                "hora_inicio": "10:00",
                "hora_fim": "14:00",
                "unidade": self.unidade.pk,
            },
        )

        destinatarios = [email for mensagem in mail.outbox for email in mensagem.to]
        self.assertIn(self.morador.email, destinatarios)
        self.assertIn(self.sindico.email, destinatarios)

    def test_cancelamento_avisa_administracao(self):
        reserva = criar_reserva(
            self.condominio, self.local, self.unidade, self.morador
        )
        self.client.force_login(self.morador)
        mail.outbox.clear()

        self.client.post(
            reverse(
                "cancelar_reserva",
                kwargs={"slug": self.condominio.slug, "pk": reserva.pk},
            )
        )

        self.assertTrue(mail.outbox)
        self.assertIn(self.sindico.email, mail.outbox[0].to)
        reserva.refresh_from_db()
        self.assertEqual(reserva.status, Reserva.Status.CANCELADA)


@override_settings(EMAIL_BACKEND=BACKEND_EMAIL)
class ProcessarPrazosTests(TestCase):
    def setUp(self):
        self.condominio, self.local, self.unidade = criar_base()
        self.morador = criar_morador(self.unidade)
        self.sindico = criar_sindico(self.condominio, self.unidade)

    def test_expira_reserva_sem_comprovante(self):
        reserva = criar_reserva(
            self.condominio, self.local, self.unidade, self.morador
        )
        reserva.expira_em = timezone.now() - timedelta(minutes=5)
        reserva.save(update_fields=["expira_em"])

        resumo = processar_prazos()

        reserva.refresh_from_db()
        self.assertEqual(reserva.status, Reserva.Status.EXPIRADA)
        self.assertEqual(resumo["expiradas"], 1)
        destinatarios = [email for mensagem in mail.outbox for email in mensagem.to]
        self.assertIn(self.morador.email, destinatarios)
        self.assertIn(self.sindico.email, destinatarios)

    def test_alerta_prazo_vencido_uma_unica_vez(self):
        reserva = criar_reserva(
            self.condominio,
            self.local,
            self.unidade,
            self.morador,
            status=Reserva.Status.EM_ANALISE,
        )
        reserva.prazo_analise_em = timezone.now() - timedelta(minutes=5)
        reserva.save(update_fields=["prazo_analise_em"])

        primeiro = processar_prazos()
        segundo = processar_prazos()

        reserva.refresh_from_db()
        self.assertEqual(primeiro["prazos_vencidos"], 1)
        self.assertEqual(segundo["prazos_vencidos"], 0)
        self.assertTrue(reserva.prazo_alertado)
        self.assertEqual(reserva.status, Reserva.Status.EM_ANALISE)
        self.assertEqual(len(mail.outbox), 1)

    def test_politica_cancelar_libera_o_horario(self):
        configuracao = ConfiguracaoCondominio.objects.get(condominio=self.condominio)
        configuracao.politica_prazo_analise = (
            ConfiguracaoCondominio.PoliticaPrazo.CANCELAR
        )
        configuracao.save(update_fields=["politica_prazo_analise"])
        reserva = criar_reserva(
            self.condominio,
            self.local,
            self.unidade,
            self.morador,
            status=Reserva.Status.EM_ANALISE,
        )
        reserva.prazo_analise_em = timezone.now() - timedelta(minutes=5)
        reserva.save(update_fields=["prazo_analise_em"])

        processar_prazos()

        reserva.refresh_from_db()
        self.assertEqual(reserva.status, Reserva.Status.EXPIRADA)

    def test_lembrete_do_dia_seguinte_envia_uma_vez(self):
        reserva = criar_reserva(
            self.condominio,
            self.local,
            self.unidade,
            self.morador,
            status=Reserva.Status.CONFIRMADA,
        )
        amanha = timezone.localtime(timezone.now()).date() + timedelta(days=1)
        inicio = timezone.make_aware(datetime.combine(amanha, time(hour=10)))
        reserva.inicio = inicio
        reserva.fim = inicio + timedelta(hours=4)
        reserva.save(update_fields=["inicio", "fim"])

        primeiro = processar_prazos()
        segundo = processar_prazos()

        reserva.refresh_from_db()
        self.assertEqual(primeiro["lembretes"], 1)
        self.assertEqual(segundo["lembretes"], 0)
        self.assertTrue(reserva.lembrete_enviado)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(reserva.local.nome, mail.outbox[0].subject)


class EndpointTarefasTests(TestCase):
    @override_settings(TAREFAS_TOKEN="segredo-de-teste")
    def test_token_correto_executa(self):
        resposta = self.client.get(
            reverse("tarefas_prazos", kwargs={"token": "segredo-de-teste"})
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.json()["ok"])

    @override_settings(TAREFAS_TOKEN="segredo-de-teste")
    def test_token_errado_retorna_404(self):
        resposta = self.client.get(
            reverse("tarefas_prazos", kwargs={"token": "outro"})
        )

        self.assertEqual(resposta.status_code, 404)

    @override_settings(TAREFAS_TOKEN="")
    def test_sem_token_configurado_retorna_404(self):
        resposta = self.client.get(reverse("tarefas_prazos", kwargs={"token": "x"}))

        self.assertEqual(resposta.status_code, 404)
