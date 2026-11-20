import secrets
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from .segredos import criptografar, descriptografar
from .storage import armazenamento_privado


def novo_segredo_webhook() -> str:
    return secrets.token_hex(32)


class Plano(models.Model):
    nome = models.CharField(max_length=60)
    slug = models.SlugField(max_length=60, unique=True)
    ordem = models.PositiveSmallIntegerField(default=1)
    preco_mensal = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    limite_unidades = models.PositiveIntegerField(
        default=0, help_text="0 significa ilimitado."
    )
    limite_locais = models.PositiveIntegerField(
        default=0, help_text="0 significa ilimitado."
    )
    descricao = models.CharField(max_length=200, blank=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["ordem", "preco_mensal"]
        verbose_name = "plano"
        verbose_name_plural = "planos"

    def __str__(self) -> str:
        return self.nome

    @classmethod
    def para_quantidade(cls, unidades: int):
        planos = cls.objects.filter(ativo=True).order_by("ordem")
        for plano in planos:
            if plano.limite_unidades == 0 or unidades <= plano.limite_unidades:
                return plano
        return planos.last()


class Condominio(models.Model):
    nome = models.CharField(max_length=120)
    slug = models.SlugField(max_length=60, unique=True)
    logo = models.ImageField(upload_to="condominios/logos/", blank=True)
    ativo = models.BooleanField(default=True)
    plano = models.ForeignKey(
        Plano,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="condominios",
    )
    trial_ate = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Fim do período de teste. Em branco significa sem prazo de teste.",
    )
    assinatura_valida_ate = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Fim do período pago, incluindo a carência.",
    )
    vencimento_em = models.DateField(
        null=True,
        blank=True,
        help_text="Próximo vencimento mensal do plano.",
    )
    dia_vencimento = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Dia mensal escolhido para vencimento (1 a 28).",
    )
    ultimo_aviso_vencimento = models.DateField(
        null=True,
        blank=True,
        help_text="Último dia em que o aviso de vencimento foi enviado.",
    )
    isento_assinatura = models.BooleanField(
        default=False,
        help_text="Libera o acesso sem cobrança (condomínios internos ou de teste).",
    )
    trial_ip_hash = models.CharField(max_length=64, blank=True)
    trial_telefone_hash = models.CharField(max_length=64, blank=True)
    trial_email_hash = models.CharField(max_length=64, blank=True)
    trial_dispositivo_hash = models.CharField(max_length=64, blank=True)
    quantidade_unidades = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Quantidade de lotes, apartamentos ou casas do condomínio. "
            "0 usa a contagem de unidades cadastradas."
        ),
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "condomínio"
        verbose_name_plural = "condomínios"

    def __str__(self) -> str:
        return self.nome

    @property
    def em_trial(self) -> bool:
        return self.trial_ate is not None and timezone.now() < self.trial_ate

    @property
    def dias_de_trial(self) -> int:
        if not self.em_trial:
            return 0
        return max(0, (self.trial_ate - timezone.now()).days)

    @property
    def assinatura_ativa(self) -> bool:
        return bool(
            self.assinatura_valida_ate
            and self.assinatura_valida_ate > timezone.now()
        )

    @property
    def carencia_dias(self) -> int:
        return max(0, int(getattr(settings, "CARENCIA_DIAS", 5)))

    @property
    def sem_controle(self) -> bool:
        return bool(
            self.trial_ate is None
            and self.assinatura_valida_ate is None
            and self.vencimento_em is None
        )

    @property
    def fim_carencia(self):
        if not self.vencimento_em:
            return None
        return self.vencimento_em + timedelta(days=self.carencia_dias)

    @property
    def dias_de_atraso(self) -> int:
        if not self.vencimento_em:
            return 0
        return max(0, (timezone.localdate() - self.vencimento_em).days)

    @property
    def dias_para_vencimento(self) -> int:
        if not self.vencimento_em:
            return 0
        return (self.vencimento_em - timezone.localdate()).days

    @property
    def dias_restantes_carencia(self) -> int:
        if not self.fim_carencia:
            return 0
        return max(0, (self.fim_carencia - timezone.localdate()).days)

    @property
    def em_carencia(self) -> bool:
        return bool(self.dias_de_atraso > 0 and self.acesso_liberado)

    @property
    def acesso_liberado(self) -> bool:
        if not self.ativo:
            return False
        if self.isento_assinatura or self.sem_controle:
            return True
        if self.vencimento_em:
            return timezone.localdate() <= self.fim_carencia
        return bool(self.em_trial or self.assinatura_ativa)

    @property
    def trial_expirado(self) -> bool:
        return bool(
            self.trial_ate
            and not self.em_trial
            and not self.assinatura_ativa
            and not self.acesso_liberado
        )

    @property
    def dias_de_assinatura(self) -> int:
        if self.vencimento_em:
            return max(0, self.dias_para_vencimento)
        if not self.assinatura_ativa:
            return 0
        return max(0, (self.assinatura_valida_ate - timezone.now()).days)

    @property
    def iniciais(self) -> str:
        ignorar = {"condominio", "condomínio", "do", "da", "de", "dos", "das"}
        partes = [parte for parte in self.nome.split() if parte.lower() not in ignorar]
        if not partes:
            return self.nome[:2].upper()
        if len(partes) == 1:
            return partes[0][:2].upper()
        return (partes[0][0] + partes[1][0]).upper()


class ConfiguracaoCondominio(models.Model):
    class PixModo(models.TextChoices):
        MANUAL = "manual", "Pix manual (chave do condomínio)"
        DINAMICO = "dinamico", "Pix automático (gateway)"

    class GatewayPix(models.TextChoices):
        ASAAS = "asaas", "Asaas"
        ABACATEPAY = "abacatepay", "AbacatePay"

    class PoliticaPrazo(models.TextChoices):
        MANTER = "manter", "Manter pendente até a análise do síndico"
        CANCELAR = "cancelar", "Cancelar e liberar o horário automaticamente"
        AUTO_CONFIRMAR_SE_VERDE = (
            "auto_confirmar_se_verde",
            "Confirmar quando o comprovante conferir",
        )

    condominio = models.OneToOneField(
        Condominio, on_delete=models.CASCADE, related_name="configuracao"
    )
    antecedencia_minima_horas = models.PositiveSmallIntegerField(default=48)
    antecedencia_maxima_dias = models.PositiveSmallIntegerField(default=90)
    prazo_analise_horas = models.PositiveSmallIntegerField(
        default=24,
        help_text="Tempo que o síndico tem para analisar o comprovante.",
    )
    politica_prazo_analise = models.CharField(
        max_length=30,
        choices=PoliticaPrazo.choices,
        default=PoliticaPrazo.MANTER,
        help_text="O que acontece quando o prazo termina sem análise.",
    )
    horas_para_reenvio = models.PositiveSmallIntegerField(
        default=12,
        help_text="Tempo que o morador tem para enviar outro comprovante.",
    )
    limite_reservas_mes = models.PositiveSmallIntegerField(
        default=2, help_text="Use 0 para ilimitado."
    )

    pix_modo = models.CharField(max_length=10, choices=PixModo.choices, default=PixModo.MANUAL)
    pix_gateway = models.CharField(max_length=20, choices=GatewayPix.choices, blank=True)
    pix_dinamico_ativo = models.BooleanField(default=False)
    auto_confirmar_ocr = models.BooleanField(default=False)
    pix_gateway_api_key_cripto = models.TextField(blank=True, editable=False)
    pix_gateway_webhook_secret = models.CharField(
        max_length=64,
        default=novo_segredo_webhook,
        editable=False,
        help_text="Segredo enviado pela AbacatePay em cada webhook deste condomínio.",
    )

    pix_chave = models.CharField(max_length=140, blank=True)
    pix_beneficiario = models.CharField(
        max_length=60,
        blank=True,
        help_text=(
            "Nome do titular da chave, como aparece no banco. "
            "O QR do Pix usa os primeiros 25 caracteres por padrão."
        ),
    )
    pix_cidade = models.CharField(max_length=15, blank=True)

    whatsapp_url = models.URLField(
        blank=True, help_text="Link completo do WhatsApp, por exemplo https://wa.me/5511999999999."
    )
    whatsapp_numero = models.CharField(
        max_length=20,
        blank=True,
        help_text=(
            "Só o número com DDD. O botão abre o WhatsApp da administração "
            "com a mensagem já escrita."
        ),
    )
    telegram_ativo = models.BooleanField(default=False)
    telegram_chat_id = models.CharField(max_length=64, blank=True)

    cor_primaria = models.CharField(max_length=7, default="#0E4A55")
    cor_acento = models.CharField(max_length=7, default="#A9553A")

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "configuração do condomínio"
        verbose_name_plural = "configurações dos condomínios"

    def __str__(self) -> str:
        return f"Configuração de {self.condominio.nome}"

    @property
    def whatsapp_link(self) -> str:
        from .notifications import link_whatsapp

        link = link_whatsapp(
            self.whatsapp_numero,
            "Olá! Falo pelo app Meu Condomínio e preciso de ajuda.",
        )
        return link or self.whatsapp_url

    @property
    def pix_gateway_api_key(self) -> str:
        return descriptografar(self.pix_gateway_api_key_cripto)

    @pix_gateway_api_key.setter
    def pix_gateway_api_key(self, valor: str) -> None:
        self.pix_gateway_api_key_cripto = criptografar((valor or "").strip())

    @property
    def pix_automatico_pronto(self) -> bool:
        return bool(
            self.pix_dinamico_ativo
            and self.pix_gateway == self.GatewayPix.ABACATEPAY
            and self.pix_gateway_api_key
        )

    def clean(self) -> None:
        if self.pix_dinamico_ativo and not self.pix_gateway:
            raise ValidationError(
                {"pix_gateway": "Escolha um gateway antes de ativar o Pix automático."}
            )
        if self.telegram_ativo and not self.telegram_chat_id:
            raise ValidationError(
                {"telegram_chat_id": "Informe o chat ID antes de ativar o Telegram."}
            )
        if self.prazo_analise_horas < 1:
            raise ValidationError({"prazo_analise_horas": "O prazo deve ser de ao menos 1 hora."})
        if not self.pix_dinamico_ativo:
            self.pix_modo = self.PixModo.MANUAL


class PagamentoPlano(models.Model):
    class Status(models.TextChoices):
        PENDENTE = "pendente", "Aguardando conferência"
        CONFIRMADO = "confirmado", "Confirmado"
        RECUSADO = "recusado", "Recusado"

    condominio = models.ForeignKey(
        Condominio, on_delete=models.CASCADE, related_name="pagamentos_plano"
    )
    plano = models.ForeignKey(
        Plano, on_delete=models.SET_NULL, null=True, blank=True
    )
    valor = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    dia_vencimento = models.PositiveSmallIntegerField(null=True, blank=True)
    comprovante = models.FileField(
        upload_to="planos/comprovantes/",
        storage=armazenamento_privado,
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDENTE
    )
    observacao = models.CharField(max_length=200, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    analisado_em = models.DateTimeField(null=True, blank=True)
    analisado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "pagamento de plano"
        verbose_name_plural = "pagamentos de plano"

    def __str__(self) -> str:
        return f"{self.condominio} · {self.get_status_display()}"
