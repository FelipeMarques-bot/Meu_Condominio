import tempfile
from datetime import datetime, timedelta
from decimal import Decimal

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Condominio
from apps.usuarios.models import Unidade, Usuario, VinculoUnidade

from .models import Local, Reserva


def criar_base(slug="bela-vista"):
    condominio = Condominio.objects.create(nome="Bela Vista", slug=slug)
    local = Local.objects.create(
        condominio=condominio,
        nome="Quiosque Primavera",
        slug="quiosque",
        categoria=Local.Categoria.QUIOSQUE,
        valor=Decimal("180.00"),
    )
    unidade = Unidade.objects.create(condominio=condominio, bloco="A", numero="101")
    return condominio, local, unidade


def criar_morador(unidade, username="morador"):
    usuario = Usuario.objects.create_user(
        username=username, email=f"{username}@example.com", password="Senha-Forte-2026"
    )
    VinculoUnidade.objects.create(
        usuario=usuario, unidade=unidade, papel=VinculoUnidade.Papel.MORADOR
    )
    return usuario


def criar_sindico(condominio, unidade, username="sindico"):
    usuario = Usuario.objects.create_user(
        username=username, email=f"{username}@example.com", password="Senha-Forte-2026"
    )
    VinculoUnidade.objects.create(
        usuario=usuario, unidade=unidade, papel=VinculoUnidade.Papel.SINDICO
    )
    return usuario


def criar_reserva(
    condominio,
    local,
    unidade,
    solicitante,
    status=Reserva.Status.AGUARDANDO_COMPROVANTE,
):
    inicio = timezone.localtime(timezone.now()).replace(
        hour=10, minute=0, second=0, microsecond=0
    ) + timedelta(days=3)
    return Reserva.objects.create(
        condominio=condominio,
        local=local,
        unidade=unidade,
        solicitante=solicitante,
        inicio=inicio,
        fim=inicio + timedelta(hours=4),
        valor=local.valor,
        status=status,
        expira_em=timezone.now() + timedelta(hours=2),
    )


class ReservaFlowTests(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.override_media = override_settings(MEDIA_ROOT=self.media)
        self.override_media.enable()
        self.addCleanup(self.override_media.disable)

        self.condominio, self.local, self.unidade = criar_base()
        self.morador = criar_morador(self.unidade)
        self.sindico = criar_sindico(self.condominio, self.unidade)
        self.client.force_login(self.morador)

    def _dados_reserva(self):
        alvo = timezone.localtime(timezone.now()) + timedelta(days=3)
        return {
            "data": alvo.strftime("%Y-%m-%d"),
            "hora_inicio": "10:00",
            "hora_fim": "14:00",
            "unidade": self.unidade.pk,
        }

    def test_reserva_cria_hold_e_vai_para_pagamento(self):
        resposta = self.client.post(
            reverse(
                "reservar",
                kwargs={"slug": self.condominio.slug, "local_slug": self.local.slug},
            ),
            self._dados_reserva(),
        )

        reserva = Reserva.objects.get()
        self.assertRedirects(
            resposta,
            reverse("pagamento", kwargs={"slug": self.condominio.slug, "pk": reserva.pk}),
            fetch_redirect_response=False,
        )
        self.assertEqual(reserva.status, Reserva.Status.AGUARDANDO_COMPROVANTE)
        self.assertIsNotNone(reserva.expira_em)
        self.assertEqual(reserva.valor, self.local.valor)

    def test_conflito_de_horario_e_recusado(self):
        dados = self._dados_reserva()
        self.client.post(
            reverse(
                "reservar",
                kwargs={"slug": self.condominio.slug, "local_slug": self.local.slug},
            ),
            dados,
        )

        resposta = self.client.post(
            reverse(
                "reservar",
                kwargs={"slug": self.condominio.slug, "local_slug": self.local.slug},
            ),
            dados,
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(Reserva.objects.count(), 1)
        self.assertContains(resposta, "já está reservado")

    def test_hold_vencido_libera_o_horario(self):
        reserva = criar_reserva(
            self.condominio, self.local, self.unidade, self.morador
        )
        reserva.expira_em = timezone.now() - timedelta(minutes=1)
        reserva.save(update_fields=["expira_em"])

        resposta = self.client.post(
            reverse(
                "reservar",
                kwargs={"slug": self.condominio.slug, "local_slug": self.local.slug},
            ),
            self._dados_reserva(),
        )

        self.assertEqual(resposta.status_code, 302)
        reserva.refresh_from_db()
        self.assertEqual(reserva.status, Reserva.Status.EXPIRADA)
        self.assertEqual(
            Reserva.objects.filter(status=Reserva.Status.AGUARDANDO_COMPROVANTE).count(), 1
        )

    def test_envio_de_comprovante_coloca_em_analise(self):
        reserva = criar_reserva(
            self.condominio, self.local, self.unidade, self.morador
        )
        arquivo = SimpleUploadedFile(
            "comprovante.png",
            b"\x89PNG\r\n\x1a\nconteudo-fake",
            content_type="image/png",
        )

        resposta = self.client.post(

            reverse(
                "enviar_comprovante",
                kwargs={"slug": self.condominio.slug, "pk": reserva.pk},
            ),
            {"comprovante": arquivo},
        )

        reserva.refresh_from_db()
        self.assertRedirects(
            resposta,
            reverse("reserva_detalhe", kwargs={"slug": self.condominio.slug, "pk": reserva.pk}),
            fetch_redirect_response=False,
        )
        self.assertEqual(reserva.status, Reserva.Status.EM_ANALISE)
        self.assertIsNotNone(reserva.prazo_analise_em)
        self.assertIsNotNone(reserva.comprovante_enviado_em)

    def test_comprovante_recusado_quando_hold_expirou(self):
        reserva = criar_reserva(
            self.condominio, self.local, self.unidade, self.morador
        )
        reserva.expira_em = timezone.now() - timedelta(minutes=1)
        reserva.save(update_fields=["expira_em"])
        arquivo = SimpleUploadedFile(
            "comprovante.png",
            b"\x89PNG\r\n\x1a\nconteudo-fake",
            content_type="image/png",
        )

        self.client.post(

            reverse(
                "enviar_comprovante",
                kwargs={"slug": self.condominio.slug, "pk": reserva.pk},
            ),
            {"comprovante": arquivo},
        )

        reserva.refresh_from_db()
        self.assertEqual(reserva.status, Reserva.Status.EXPIRADA)
        self.assertIsNone(reserva.prazo_analise_em)

    def test_pagina_de_pagamento_mostra_qr_quando_pix_configurado(self):
        reserva = criar_reserva(
            self.condominio, self.local, self.unidade, self.morador
        )
        configuracao = self.condominio.configuracao
        configuracao.pix_chave = "pix@bela-vista.com.br"
        configuracao.pix_beneficiario = "Bela Vista"
        configuracao.pix_cidade = "Sao Paulo"
        configuracao.save()

        resposta = self.client.get(
            reverse("pagamento", kwargs={"slug": self.condominio.slug, "pk": reserva.pk})
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "data:image/png;base64")
        self.assertContains(resposta, "pix@bela-vista.com.br")

    def test_morador_nao_acessa_painel(self):
        resposta = self.client.get(
            reverse("painel", kwargs={"slug": self.condominio.slug})
        )

        self.assertEqual(resposta.status_code, 403)

    def test_paginas_do_morador_renderizam(self):
        reserva = criar_reserva(
            self.condominio, self.local, self.unidade, self.morador
        )
        urls = [
            reverse("minhas_reservas", kwargs={"slug": self.condominio.slug}),
            reverse(
                "reserva_detalhe",
                kwargs={"slug": self.condominio.slug, "pk": reserva.pk},
            ),
            reverse(
                "pagamento",
                kwargs={"slug": self.condominio.slug, "pk": reserva.pk},
            ),
        ]

        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_morador_nao_ve_reserva_de_outra_unidade(self):
        outra_unidade = Unidade.objects.create(
            condominio=self.condominio, bloco="B", numero="202"
        )
        outro_morador = criar_morador(outra_unidade, username="vizinho")
        reserva = criar_reserva(
            self.condominio, self.local, outra_unidade, outro_morador
        )

        resposta = self.client.get(
            reverse("reserva_detalhe", kwargs={"slug": self.condominio.slug, "pk": reserva.pk})
        )

        self.assertEqual(resposta.status_code, 403)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AnaliseReservaTests(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.override_media = override_settings(MEDIA_ROOT=self.media)
        self.override_media.enable()
        self.addCleanup(self.override_media.disable)

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
        self.reserva.comprovante = "comprovantes/teste.png"
        self.reserva.save(update_fields=["comprovante"])
        self.client.force_login(self.sindico)

    def test_confirmar_gera_codigo_e_avisa_morador(self):
        resposta = self.client.post(
            reverse(
                "confirmar_reserva",
                kwargs={"slug": self.condominio.slug, "pk": self.reserva.pk},
            ),
            {"confirmo_analise": "on"},
        )

        self.reserva.refresh_from_db()
        self.assertRedirects(
            resposta, reverse("painel", kwargs={"slug": self.condominio.slug})
        )
        self.assertEqual(self.reserva.status, Reserva.Status.CONFIRMADA)
        self.assertEqual(len(self.reserva.codigo_checkin), 6)
        self.assertIsNotNone(self.reserva.confirmado_em)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.reserva.codigo_checkin, mail.outbox[0].body)

    def test_confirmar_exige_conferencia_do_comprovante(self):
        resposta = self.client.post(
            reverse(
                "confirmar_reserva",
                kwargs={"slug": self.condominio.slug, "pk": self.reserva.pk},
            )
        )

        self.reserva.refresh_from_db()
        self.assertEqual(self.reserva.status, Reserva.Status.EM_ANALISE)
        self.assertRedirects(
            resposta,
            reverse(
                "analise_reserva",
                kwargs={"slug": self.condominio.slug, "pk": self.reserva.pk},
            ),
            fetch_redirect_response=False,
        )

    def test_confirmar_bloqueia_conflito_com_outra_confirmada(self):
        criar_reserva(
            self.condominio,
            self.local,
            self.unidade,
            self.morador,
            status=Reserva.Status.CONFIRMADA,
        )

        self.client.post(
            reverse(
                "confirmar_reserva",
                kwargs={"slug": self.condominio.slug, "pk": self.reserva.pk},
            ),
            {"confirmo_analise": "on"},
        )

        self.reserva.refresh_from_db()
        self.assertEqual(self.reserva.status, Reserva.Status.EM_ANALISE)

    def test_recusar_exige_motivo(self):
        resposta = self.client.post(
            reverse(
                "rejeitar_reserva",
                kwargs={"slug": self.condominio.slug, "pk": self.reserva.pk},
            ),
            {"motivo": "   "},
        )

        self.reserva.refresh_from_db()
        self.assertEqual(self.reserva.status, Reserva.Status.EM_ANALISE)
        self.assertRedirects(
            resposta,
            reverse(
                "analise_reserva",
                kwargs={"slug": self.condominio.slug, "pk": self.reserva.pk},
            ),
            fetch_redirect_response=False,
        )

    def test_recusar_com_motivo_avisa_morador(self):
        self.client.post(
            reverse(
                "rejeitar_reserva",
                kwargs={"slug": self.condominio.slug, "pk": self.reserva.pk},
            ),
            {"motivo": "Valor divergente do comprovante."},
        )

        self.reserva.refresh_from_db()
        self.assertEqual(self.reserva.status, Reserva.Status.REJEITADA)
        self.assertEqual(self.reserva.motivo_rejeicao, "Valor divergente do comprovante.")
        self.assertEqual(len(mail.outbox), 1)

    def test_painel_lista_pendentes(self):
        resposta = self.client.get(reverse("painel", kwargs={"slug": self.condominio.slug}))

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, self.local.nome)
        self.assertContains(resposta, "Em análise")

    def test_pagina_de_analise_renderiza_comprovante(self):
        resposta = self.client.get(
            reverse(
                "analise_reserva",
                kwargs={"slug": self.condominio.slug, "pk": self.reserva.pk},
            )
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Comprovante")
        self.assertContains(resposta, "Confirmar reserva")

    def test_configuracoes_renderizam(self):
        resposta = self.client.get(
            reverse("configuracoes", kwargs={"slug": self.condominio.slug})
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Pix da reserva")


class AgendaTests(TestCase):
    def test_visitante_ve_convite_para_entrar(self):
        condominio, local, _ = criar_base()

        resposta = self.client.get(reverse("agenda", kwargs={"slug": condominio.slug}))

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Entrar para reservar")

class CalendarioTests(TestCase):
    def setUp(self):
        self.condominio, self.local, self.unidade = criar_base()
        self.morador = criar_morador(self.unidade)
        self.client.force_login(self.morador)

    def _url(self):
        return reverse("minhas_reservas", kwargs={"slug": self.condominio.slug})

    def _reserva(self, inicio, unidade=None, solicitante=None):
        return Reserva.objects.create(
            condominio=self.condominio,
            local=self.local,
            unidade=unidade or self.unidade,
            solicitante=solicitante or self.morador,
            inicio=inicio,
            fim=inicio + timedelta(hours=2),
            valor=self.local.valor,
            status=Reserva.Status.CONFIRMADA,
        )

    def _dias(self, resposta):
        return [
            dia
            for semana in resposta.context["calendario"]["semanas"]
            for dia in semana
        ]

    def test_mes_escolhido_mostra_reserva_no_dia(self):
        inicio = timezone.make_aware(datetime(2026, 3, 10, 10, 0))
        self._reserva(inicio)

        resposta = self.client.get(self._url(), {"mes": "2026-03"})

        calendario = resposta.context["calendario"]
        self.assertEqual(calendario["titulo"], "Março de 2026")
        dia = next(d for d in self._dias(resposta) if d["no_mes"] and d["numero"] == 10)
        self.assertEqual(len(dia["reservas"]), 1)
        self.assertEqual(calendario["total"], 1)
        self.assertContains(resposta, "mes=2026-04")

    def test_mes_vazio_nao_mostra_reserva_de_outro_mes(self):
        self._reserva(timezone.make_aware(datetime(2026, 4, 2, 10, 0)))

        resposta = self.client.get(self._url(), {"mes": "2026-03"})

        self.assertEqual(resposta.context["calendario"]["total"], 0)

    def test_mes_invalido_cai_no_mes_atual(self):
        hoje = timezone.localdate()

        resposta = self.client.get(self._url(), {"mes": "2026-13"})

        self.assertEqual(
            resposta.context["calendario"]["valor"], hoje.strftime("%Y-%m")
        )

    def test_reserva_de_outra_unidade_aparece_como_ocupada_sem_identidade(self):
        outra = Unidade.objects.create(
            condominio=self.condominio, bloco="C", numero="301"
        )
        outro = criar_morador(outra, username="vizinho-calendario")
        self._reserva(
            timezone.make_aware(datetime(2026, 3, 12, 10, 0)),
            unidade=outra,
            solicitante=outro,
        )

        resposta = self.client.get(self._url(), {"mes": "2026-03"})

        calendario = resposta.context["calendario"]
        self.assertEqual(calendario["total"], 1)
        dia = next(d for d in self._dias(resposta) if d["numero"] == 12)
        self.assertEqual(len(dia["reservas"]), 1)
        evento = dia["reservas"][0]
        self.assertFalse(evento["propria"])
        self.assertEqual(evento["status"], "Ocupado")
        self.assertNotIn("Vizinho", resposta.content.decode())
        self.assertNotIn("301", resposta.content.decode())

    def test_dia_selecionado_traz_rotulo_e_eventos(self):
        inicio = timezone.make_aware(datetime(2026, 3, 10, 10, 0))
        self._reserva(inicio)

        resposta = self.client.get(self._url(), {"mes": "2026-03"})

        dias = resposta.context["calendario"]["dias"]
        self.assertIn("2026-03-10", dias)
        info = dias["2026-03-10"]
        self.assertIn("10 de março", info["rotulo"])
        self.assertEqual(len(info["eventos"]), 1)
        self.assertTrue(info["eventos"][0]["propria"])


class ComprovantePrivadoTests(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.override_media = override_settings(MEDIA_ROOT=self.media)
        self.override_media.enable()
        self.addCleanup(self.override_media.disable)

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
        self.reserva.comprovante = SimpleUploadedFile(
            "comprovante.png", b"conteudo-privado", content_type="image/png"
        )
        self.reserva.save(update_fields=["comprovante"])
        self.url = reverse(
            "baixar_comprovante",
            kwargs={"slug": self.condominio.slug, "pk": self.reserva.pk},
        )

    def test_comprovante_nao_tem_url_publica(self):
        with self.assertRaises(ValueError):
            url = self.reserva.comprovante.url
            self.assertIsNone(url)

    def test_arquivo_fica_fora_da_media_publica(self):
        caminho = self.reserva.comprovante.path
        self.assertIn("privado", caminho)
        self.assertTrue(caminho.endswith("comprovante.png"))

    def test_morador_baixa_o_proprio_comprovante(self):
        self.client.force_login(self.morador)

        resposta = self.client.get(self.url)

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(b"".join(resposta.streaming_content), b"conteudo-privado")

    def test_sindico_baixa_comprovante(self):
        self.client.force_login(self.sindico)

        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_outro_morador_nao_baixa(self):
        outra = Unidade.objects.create(
            condominio=self.condominio, bloco="C", numero="301"
        )
        vizinho = criar_morador(outra, username="vizinho")
        self.client.force_login(vizinho)

        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_visitante_e_redirecionado_para_login(self):
        resposta = self.client.get(self.url)

        self.assertEqual(resposta.status_code, 302)
        self.assertIn("/entrar/", resposta["Location"])

    def test_reserva_sem_comprovante_retorna_404(self):
        self.reserva.comprovante.delete()
        self.reserva.comprovante = ""
        self.reserva.save(update_fields=["comprovante"])
        self.client.force_login(self.morador)

        self.assertEqual(self.client.get(self.url).status_code, 404)


class ResultadoAnaliseAvisoTests(TestCase):
    def setUp(self):
        self.condominio, self.local, self.unidade = criar_base()
        self.morador = criar_morador(self.unidade)
        self.reserva = criar_reserva(
            self.condominio,
            self.local,
            self.unidade,
            self.morador,
            status=Reserva.Status.CONFIRMADA,
        )
        self.client.force_login(self.morador)

    def test_morador_ve_aviso_ate_marcar_como_visto(self):
        resposta = self.client.get(
            reverse("agenda", kwargs={"slug": self.condominio.slug})
        )

        self.assertContains(resposta, "Reserva confirmada!")
        self.assertContains(resposta, "Ver minhas reservas")

        self.client.post(
            reverse(
                "marcar_resultados_vistos",
                kwargs={"slug": self.condominio.slug},
            )
        )

        self.reserva.refresh_from_db()
        self.assertIsNotNone(self.reserva.resultado_visto_em)
        resposta = self.client.get(
            reverse("agenda", kwargs={"slug": self.condominio.slug})
        )
        self.assertNotContains(resposta, "Reserva confirmada!")

    def test_abrir_detalhe_marca_resultado_como_visto(self):
        self.client.get(
            reverse(
                "reserva_detalhe",
                kwargs={"slug": self.condominio.slug, "pk": self.reserva.pk},
            )
        )

        self.reserva.refresh_from_db()
        self.assertIsNotNone(self.reserva.resultado_visto_em)

class ConfirmarUsoComFotoTests(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.override_media = override_settings(MEDIA_ROOT=self.media)
        self.override_media.enable()
        self.addCleanup(self.override_media.disable)

        self.condominio, self.local, self.unidade = criar_base()
        self.morador = criar_morador(self.unidade)
        self.sindico = criar_sindico(self.condominio, self.unidade)

        hoje = timezone.localtime()
        self.inicio = hoje.replace(hour=10, minute=0, second=0, microsecond=0)
        self.reserva = Reserva.objects.create(
            condominio=self.condominio,
            local=self.local,
            unidade=self.unidade,
            solicitante=self.morador,
            inicio=self.inicio,
            fim=self.inicio + timedelta(hours=4),
            valor=self.local.valor,
            status=Reserva.Status.CONFIRMADA,
            codigo_checkin="ABC123",
        )
        self.url = reverse(
            "confirmar_uso",
            kwargs={"slug": self.condominio.slug, "pk": self.reserva.pk},
        )
        self.client.force_login(self.morador)

    def _foto(self, nome="uso.jpg"):
        return SimpleUploadedFile(
            nome, b"\xff\xd8\xff\xe0foto-de-teste", content_type="image/jpeg"
        )

    def test_pagina_pede_foto_com_camera(self):
        resposta = self.client.get(self.url)

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'capture="environment"')
        self.assertContains(resposta, "Foto do espaço (obrigatória)")

    def test_sem_foto_nao_registra_checkin(self):
        resposta = self.client.post(self.url, {})

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Tire uma foto do espaço")
        self.reserva.refresh_from_db()
        self.assertIsNone(self.reserva.checkin_em)
        self.assertFalse(self.reserva.checkin_foto)

    def test_com_foto_registra_uso(self):
        resposta = self.client.post(self.url, {"foto": self._foto()})

        self.assertEqual(resposta.status_code, 302)
        self.reserva.refresh_from_db()
        self.assertIsNotNone(self.reserva.checkin_em)
        self.assertTrue(self.reserva.checkin_foto)
        self.assertEqual(self.reserva.checkin_por, self.morador)

    def test_fora_do_dia_da_reserva_nao_permite(self):
        amanha = timezone.localtime() + timedelta(days=1)
        self.reserva.inicio = amanha.replace(hour=10, minute=0, second=0, microsecond=0)
        self.reserva.fim = self.reserva.inicio + timedelta(hours=4)
        self.reserva.save(update_fields=["inicio", "fim"])

        self.client.post(self.url, {"foto": self._foto()})

        self.reserva.refresh_from_db()
        self.assertIsNone(self.reserva.checkin_em)

    def test_sindico_nao_fecha_checkin_sem_foto_do_morador(self):
        self.client.force_login(self.sindico)

        resposta = self.client.post(
            reverse("checkin", kwargs={"slug": self.condominio.slug}),
            {"codigo": "ABC123"},
            follow=True,
        )

        self.assertContains(resposta, "ainda não confirmou o uso com foto")
        self.reserva.refresh_from_db()
        self.assertIsNone(self.reserva.checkin_em)

    def test_sindico_fecha_checkin_depois_da_foto(self):
        self.client.post(self.url, {"foto": self._foto()})
        self.reserva.refresh_from_db()
        self.reserva.checkin_em = None
        self.reserva.save(update_fields=["checkin_em"])

        self.client.force_login(self.sindico)
        resposta = self.client.post(
            reverse("checkin", kwargs={"slug": self.condominio.slug}),
            {"codigo": "ABC123"},
            follow=True,
        )

        self.assertContains(resposta, "Check-in confirmado")
        self.reserva.refresh_from_db()
        self.assertIsNotNone(self.reserva.checkin_em)
