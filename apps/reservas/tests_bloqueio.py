from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.usuarios.models import Unidade, VinculoUnidade

from .models import ListaEspera, Reserva
from .tests import criar_base, criar_morador


class BloqueioDeReservasTests(TestCase):
    def setUp(self):
        self.condominio, self.local, self.unidade = criar_base()
        self.morador = criar_morador(self.unidade)
        self.vinculo = VinculoUnidade.objects.get(
            usuario=self.morador, unidade=self.unidade
        )
        self.data = timezone.localdate() + timedelta(days=4)
        self.url_reservar = reverse(
            "reservar", args=[self.condominio.slug, self.local.slug]
        )
        self.url_espera = reverse(
            "entrar_na_espera", args=[self.condominio.slug, self.local.slug]
        )

    def _dados(self, unidade=None):
        return {
            "data": self.data.isoformat(),
            "hora_inicio": "10:00",
            "hora_fim": "12:00",
            "unidade": (unidade or self.unidade).pk,
        }

    def _bloquear(self):
        self.vinculo.bloqueio_reservas = True
        self.vinculo.save(update_fields=["bloqueio_reservas"])

    def test_morador_bloqueado_ve_mensagem_e_nao_reserva(self):
        self._bloquear()
        self.client.force_login(self.morador)

        resposta = self.client.get(self.url_reservar)

        self.assertContains(resposta, "Entre em contato com o administrador ou síndico")
        self.assertNotContains(resposta, 'name="unidade"')

        self.client.post(self.url_reservar, self._dados())

        self.assertFalse(Reserva.objects.exists())

    def test_bloqueio_tambem_impide_lista_de_espera(self):
        self._bloquear()
        self.client.force_login(self.morador)

        resposta = self.client.post(
            self.url_espera,
            {"data": self.data.isoformat(), "unidade": self.unidade.pk},
            follow=True,
        )

        self.assertFalse(ListaEspera.objects.exists())
        self.assertContains(resposta, "Reservas bloqueadas")

    def test_outro_lote_livre_pode_reservar(self):
        outro_lote = Unidade.objects.create(
            condominio=self.condominio, bloco="A", numero="102"
        )
        VinculoUnidade.objects.create(
            usuario=self.morador,
            unidade=outro_lote,
            papel=VinculoUnidade.Papel.MORADOR,
        )
        self._bloquear()
        self.client.force_login(self.morador)

        resposta = self.client.post(self.url_reservar, self._dados(outro_lote))

        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(Reserva.objects.filter(unidade=outro_lote).exists())
