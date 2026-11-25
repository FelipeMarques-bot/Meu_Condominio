from datetime import timedelta

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.notifications import link_whatsapp

from .models import ListaEspera, Reserva
from .prazos import processar_prazos
from .resultados import resultados_nao_vistos
from .tests import criar_base, criar_morador, criar_reserva, criar_sindico

BACKEND_EMAIL = "django.core.mail.backends.locmem.EmailBackend"


@override_settings(EMAIL_BACKEND=BACKEND_EMAIL)
class ListaEsperaTests(TestCase):
    def setUp(self):
        self.condominio, self.local, self.unidade = criar_base()
        self.morador = criar_morador(self.unidade)
        self.sindico = criar_sindico(self.condominio, self.unidade)

    def _entrar(self, data):
        return self.client.post(
            reverse(
                "entrar_na_espera",
                kwargs={"slug": self.condominio.slug, "local_slug": self.local.slug},
            ),
            {"data": data.strftime("%Y-%m-%d"), "unidade": self.unidade.pk},
        )

    def test_morador_entra_na_lista(self):
        self.client.force_login(self.morador)
        amanha = timezone.localdate() + timedelta(days=1)

        self._entrar(amanha)

        entrada = ListaEspera.objects.get()
        self.assertEqual(entrada.data, amanha)
        self.assertEqual(entrada.solicitante, self.morador)
        self.assertEqual(entrada.status, ListaEspera.Status.AGUARDANDO)

    def test_data_passada_e_recusada(self):
        self.client.force_login(self.morador)
        ontem = timezone.localdate() - timedelta(days=1)

        self._entrar(ontem)

        self.assertFalse(ListaEspera.objects.exists())

    def test_morador_sai_da_lista(self):
        self.client.force_login(self.morador)
        entrada = ListaEspera.objects.create(
            condominio=self.condominio,
            local=self.local,
            unidade=self.unidade,
            solicitante=self.morador,
            data=timezone.localdate() + timedelta(days=2),
        )

        self.client.post(
            reverse(
                "cancelar_espera",
                kwargs={"slug": self.condominio.slug, "pk": entrada.pk},
            )
        )

        entrada.refresh_from_db()
        self.assertEqual(entrada.status, ListaEspera.Status.CANCELADO)

    def test_cancelamento_avisa_quem_espera(self):
        entrada = ListaEspera.objects.create(
            condominio=self.condominio,
            local=self.local,
            unidade=self.unidade,
            solicitante=self.morador,
            data=timezone.localtime().date() + timedelta(days=3),
        )
        reserva = criar_reserva(
            self.condominio, self.local, self.unidade, self.sindico
        )
        entrada.data = timezone.localtime(reserva.inicio).date()
        entrada.save(update_fields=["data"])
        self.client.force_login(self.morador)
        mail.outbox.clear()

        self.client.post(
            reverse(
                "cancelar_reserva",
                kwargs={"slug": self.condominio.slug, "pk": reserva.pk},
            )
        )

        entrada.refresh_from_db()
        self.assertEqual(entrada.status, ListaEspera.Status.AVISADO)
        assuntos = [mensagem.subject for mensagem in mail.outbox]
        self.assertTrue(any("Vaga liberada" in assunto for assunto in assuntos))

    def test_expiracao_avisa_quem_espera(self):
        entrada = ListaEspera.objects.create(
            condominio=self.condominio,
            local=self.local,
            unidade=self.unidade,
            solicitante=self.morador,
            data=timezone.localtime().date() + timedelta(days=3),
        )
        reserva = criar_reserva(
            self.condominio, self.local, self.unidade, self.sindico
        )
        entrada.data = timezone.localtime(reserva.inicio).date()
        entrada.save(update_fields=["data"])
        reserva.expira_em = timezone.now() - timedelta(minutes=1)
        reserva.save(update_fields=["expira_em"])
        mail.outbox.clear()

        processar_prazos()

        entrada.refresh_from_db()
        self.assertEqual(entrada.status, ListaEspera.Status.AVISADO)

    def test_recusa_tambem_libera_vaga_para_lista_de_espera(self):
        entrada = ListaEspera.objects.create(
            condominio=self.condominio,
            local=self.local,
            unidade=self.unidade,
            solicitante=self.morador,
            data=timezone.localdate() + timedelta(days=3),
        )
        reserva = criar_reserva(
            self.condominio,
            self.local,
            self.unidade,
            self.sindico,
            status=Reserva.Status.EM_ANALISE,
        )
        entrada.data = timezone.localtime(reserva.inicio).date()
        entrada.save(update_fields=["data"])
        self.client.force_login(self.sindico)
        mail.outbox.clear()

        self.client.post(
            reverse(
                "rejeitar_reserva",
                kwargs={"slug": self.condominio.slug, "pk": reserva.pk},
            ),
            {"motivo": "Comprovante ilegível"},
        )

        entrada.refresh_from_db()
        self.assertEqual(entrada.status, ListaEspera.Status.AVISADO)
        self.assertTrue(any("Vaga liberada" in m.subject for m in mail.outbox))

    def test_painel_do_sindico_mostra_lista_de_espera(self):
        ListaEspera.objects.create(
            condominio=self.condominio,
            local=self.local,
            unidade=self.unidade,
            solicitante=self.morador,
            data=timezone.localdate() + timedelta(days=2),
        )
        self.client.force_login(self.sindico)

        resposta = self.client.get(
            reverse("painel", kwargs={"slug": self.condominio.slug})
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Lista de espera")
        self.assertContains(resposta, self.local.nome)

    def test_vaga_liberada_aparece_no_app_e_pode_ser_marcada_como_vista(self):
        entrada = ListaEspera.objects.create(
            condominio=self.condominio,
            local=self.local,
            unidade=self.unidade,
            solicitante=self.morador,
            data=timezone.localdate() + timedelta(days=2),
            status=ListaEspera.Status.AVISADO,
            avisado_em=timezone.now(),
        )
        self.client.force_login(self.morador)
        url = reverse("minhas_reservas", kwargs={"slug": self.condominio.slug})

        resposta = self.client.get(url)
        self.assertContains(resposta, "Sua vaga liberou!")

        self.client.post(
            reverse("marcar_esperas_vistas", kwargs={"slug": self.condominio.slug})
        )
        entrada.refresh_from_db()
        self.assertIsNotNone(entrada.aviso_visto_em)

        resposta = self.client.get(url)
        self.assertNotContains(resposta, "Sua vaga liberou!")


class ResultadoDaAnaliseTests(TestCase):
    def setUp(self):
        self.condominio, self.local, self.unidade = criar_base()
        self.morador = criar_morador(self.unidade)
        self.sindico = criar_sindico(self.condominio, self.unidade)
        self.reserva = criar_reserva(
            self.condominio,
            self.local,
            self.unidade,
            self.morador,
            status=Reserva.Status.EM_ANALISE,
        )
        self.motivo = (
            "O arquivo não é um comprovante de pagamento, favor inserir "
            "o comprovante para poder garantir a reserva!"
        )
        self.client.force_login(self.sindico)
        self.client.post(
            reverse(
                "rejeitar_reserva",
                kwargs={"slug": self.condominio.slug, "pk": self.reserva.pk},
            ),
            {"motivo": self.motivo},
        )

    def test_aviso_de_recusa_e_do_morador_e_nao_do_sindico(self):
        self.assertFalse(resultados_nao_vistos(self.sindico, self.condominio).exists())
        self.assertEqual(
            [item.pk for item in resultados_nao_vistos(self.morador, self.condominio)],
            [self.reserva.pk],
        )

    def test_sindico_pode_marcar_avisos_sem_apagar_o_do_morador(self):
        self.client.post(
            reverse(
                "marcar_resultados_vistos", kwargs={"slug": self.condominio.slug}
            )
        )

        self.assertTrue(resultados_nao_vistos(self.morador, self.condominio).exists())

    def test_morador_ve_motivo_da_recusa_no_aviso(self):
        self.client.force_login(self.morador)

        resposta = self.client.get(
            reverse("minhas_reservas", kwargs={"slug": self.condominio.slug})
        )

        self.assertContains(resposta, "Sua reserva foi recusada")
        self.assertContains(resposta, self.motivo)

    def test_sindico_ve_motivo_no_relatorio_de_analise(self):
        resposta = self.client.get(
            reverse(
                "analise_reserva",
                kwargs={"slug": self.condominio.slug, "pk": self.reserva.pk},
            )
        )

        self.assertContains(resposta, self.motivo)


class CheckinTests(TestCase):
    def setUp(self):
        self.condominio, self.local, self.unidade = criar_base()
        self.morador = criar_morador(self.unidade)
        self.sindico = criar_sindico(self.condominio, self.unidade)
        self.reserva = criar_reserva(
            self.condominio,
            self.local,
            self.unidade,
            self.morador,
            status=Reserva.Status.CONFIRMADA,
        )
        self.reserva.codigo_checkin = "ABC123"
        self.reserva.save(update_fields=["codigo_checkin"])

    def test_sindico_registra_checkin(self):
        self.client.force_login(self.sindico)
        self.reserva.checkin_foto = "checkins/foto-do-morador.jpg"
        self.reserva.save(update_fields=["checkin_foto"])

        resposta = self.client.post(
            reverse("checkin", kwargs={"slug": self.condominio.slug}),
            {"codigo": "abc123"},
        )

        self.assertEqual(resposta.status_code, 200)
        self.reserva.refresh_from_db()
        self.assertIsNotNone(self.reserva.checkin_em)

    def test_sem_foto_do_morador_o_codigo_nao_fecha_o_checkin(self):
        self.client.force_login(self.sindico)

        self.client.post(
            reverse("checkin", kwargs={"slug": self.condominio.slug}),
            {"codigo": "abc123"},
        )

        self.reserva.refresh_from_db()
        self.assertIsNone(self.reserva.checkin_em)

    def test_codigo_invalido_nao_registra(self):
        self.client.force_login(self.sindico)

        self.client.post(
            reverse("checkin", kwargs={"slug": self.condominio.slug}),
            {"codigo": "XXXXXX"},
        )

        self.reserva.refresh_from_db()
        self.assertIsNone(self.reserva.checkin_em)

    def test_morador_nao_acessa_checkin(self):
        self.client.force_login(self.morador)

        resposta = self.client.get(
            reverse("checkin", kwargs={"slug": self.condominio.slug})
        )

        self.assertEqual(resposta.status_code, 403)

    def test_qr_do_dono_responde_png(self):
        self.client.force_login(self.morador)

        resposta = self.client.get(
            reverse(
                "reserva_qr",
                kwargs={"slug": self.condominio.slug, "pk": self.reserva.pk},
            )
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta["Content-Type"], "image/png")


class RelatoriosTests(TestCase):
    def setUp(self):
        self.condominio, self.local, self.unidade = criar_base()
        self.morador = criar_morador(self.unidade)
        self.sindico = criar_sindico(self.condominio, self.unidade)
        criar_reserva(
            self.condominio,
            self.local,
            self.unidade,
            self.morador,
            status=Reserva.Status.CONFIRMADA,
        )

    def test_sindico_ve_relatorio(self):
        self.client.force_login(self.sindico)

        resposta = self.client.get(
            reverse("relatorios", kwargs={"slug": self.condominio.slug})
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Receita confirmada")
        self.assertContains(resposta, "Quiosque Primavera")

    def test_morador_nao_ve_relatorio(self):
        self.client.force_login(self.morador)

        resposta = self.client.get(
            reverse("relatorios", kwargs={"slug": self.condominio.slug})
        )

        self.assertEqual(resposta.status_code, 403)

    def test_relatorio_lista_recusas_e_motivos(self):
        reserva = criar_reserva(
            self.condominio,
            self.local,
            self.unidade,
            self.morador,
            status=Reserva.Status.EM_ANALISE,
        )
        self.client.force_login(self.sindico)
        self.client.post(
            reverse(
                "rejeitar_reserva",
                kwargs={"slug": self.condominio.slug, "pk": reserva.pk},
            ),
            {"motivo": "Comprovante fora do horário reservado."},
        )

        resposta = self.client.get(
            reverse("relatorios", kwargs={"slug": self.condominio.slug}),
            {"mes": timezone.localtime(reserva.inicio).strftime("%Y-%m")},
        )

        self.assertContains(resposta, "Recusas do mês")
        self.assertContains(resposta, "Comprovante fora do horário reservado.")


class WhatsAppTests(TestCase):
    def test_link_adiciona_codigo_do_pais(self):
        link = link_whatsapp("(47) 99999-0000", "Oi")

        self.assertTrue(link.startswith("https://wa.me/5547999990000"))
        self.assertIn("text=Oi", link)

    def test_sem_telefone_nao_gera_link(self):
        self.assertEqual(link_whatsapp("", "Oi"), "")
