from datetime import datetime, time, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from .forms import ReservaForm
from .models import Reserva
from .tests import criar_base, criar_morador


class LimiteMensalTests(TestCase):
    def setUp(self):
        self.condominio, self.local, self.unidade = criar_base()
        self.morador = criar_morador(self.unidade)
        configuracao = self.condominio.configuracao
        configuracao.limite_reservas_mes = 2
        configuracao.save(update_fields=["limite_reservas_mes"])

        hoje = timezone.localdate()
        self.proximo_mes = (hoje.replace(day=1) + timedelta(days=32)).replace(day=1)
        self.mes_seguinte = (self.proximo_mes + timedelta(days=32)).replace(day=1)

    def _reserva(self, dia, mes):
        inicio = timezone.make_aware(
            datetime.combine(mes.replace(day=dia), time(hour=10)),
            timezone.get_current_timezone(),
        )
        return Reserva.objects.create(
            condominio=self.condominio,
            local=self.local,
            unidade=self.unidade,
            solicitante=self.morador,
            inicio=inicio,
            fim=inicio + timedelta(hours=2),
            valor=Decimal("180.00"),
            status=Reserva.Status.CONFIRMADA,
        )

    def _form(self, dia, mes):
        return ReservaForm(
            data={
                "data": mes.replace(day=dia).isoformat(),
                "hora_inicio": "10:00",
                "hora_fim": "12:00",
                "unidade": self.unidade.pk,
            },
            condominio=self.condominio,
            usuario=self.morador,
            local=self.local,
        )

    def test_limite_usa_o_mes_da_reserva_e_nao_o_mes_vigente(self):
        self._reserva(10, self.proximo_mes)
        self._reserva(12, self.proximo_mes)

        form_no_mes_cheio = self._form(14, self.proximo_mes)
        self.assertFalse(form_no_mes_cheio.is_valid())
        self.assertTrue(
            any("limite de 2 reservas" in erro for erro in form_no_mes_cheio.errors["unidade"])
        )

        form_no_mes_livre = self._form(10, self.mes_seguinte)
        self.assertTrue(form_no_mes_livre.is_valid(), form_no_mes_livre.errors)

    def test_unidade_pode_ter_limite_proprio_ilimitado(self):
        self._reserva(10, self.proximo_mes)
        self._reserva(12, self.proximo_mes)
        self.unidade.limite_reservas_mes = 0
        self.unidade.save(update_fields=["limite_reservas_mes"])

        form = self._form(14, self.proximo_mes)
        self.assertTrue(form.is_valid(), form.errors)

    def test_unidade_pode_ter_limite_mais_rigido_que_o_condominio(self):
        self._reserva(10, self.proximo_mes)
        self.unidade.limite_reservas_mes = 1
        self.unidade.save(update_fields=["limite_reservas_mes"])

        form = self._form(14, self.proximo_mes)
        self.assertFalse(form.is_valid())
        self.assertTrue(
            any("limite de 1 reserva" in erro for erro in form.errors["unidade"])
        )
