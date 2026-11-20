from datetime import timedelta

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.usuarios.models import Unidade, Usuario, VinculoUnidade

from .models import Condominio
from .vencimentos import enviar_avisos_vencimento

SENHA = "Senha-Forte-2026"


def criar_condominio(vencimento_em, isento=False, email="sindico@example.com"):
    condominio = Condominio.objects.create(
        nome="Bela Vista",
        slug="bela-vista",
        vencimento_em=vencimento_em,
        isento_assinatura=isento,
    )
    unidade = Unidade.objects.create(
        condominio=condominio, numero="Administração", administrativa=True
    )
    usuario = Usuario.objects.create_user(
        username="sindico", email=email, password=SENHA
    )
    VinculoUnidade.objects.create(
        usuario=usuario,
        unidade=unidade,
        papel=VinculoUnidade.Papel.SINDICO,
    )
    return condominio


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    SITE_URL="https://example.com",
)
class AvisosVencimentoTests(TestCase):
    def test_envia_aviso_de_cinco_dias_uma_vez(self):
        hoje = timezone.localdate()
        condominio = criar_condominio(hoje + timedelta(days=5))

        self.assertEqual(enviar_avisos_vencimento(hoje), 1)
        self.assertEqual(enviar_avisos_vencimento(hoje), 0)

        condominio.refresh_from_db()
        self.assertEqual(condominio.ultimo_aviso_vencimento, hoje)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("vence em 5 dias", mail.outbox[0].subject)
        self.assertIn("sindico@example.com", mail.outbox[0].to)
        self.assertIn(
            "https://example.com/c/bela-vista/assinatura/",
            mail.outbox[0].body,
        )

    def test_envia_ultimo_dia_de_carencia(self):
        hoje = timezone.localdate()
        criar_condominio(hoje - timedelta(days=5))

        self.assertEqual(enviar_avisos_vencimento(hoje), 1)

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Último dia de carência", mail.outbox[0].subject)
        self.assertIn("suspenso amanhã", mail.outbox[0].body)

    def test_nao_envia_para_isento(self):
        hoje = timezone.localdate()
        criar_condominio(hoje + timedelta(days=5), isento=True)

        self.assertEqual(enviar_avisos_vencimento(hoje), 0)
        self.assertEqual(len(mail.outbox), 0)
