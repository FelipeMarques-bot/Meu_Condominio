import secrets

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from .segredos import criptografar, descriptografar


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
        MANTER = "manter", "Manter pendente e escalar"
        CANCELAR = "cancelar", "Cancelar e liberar o horário"
        AUTO_CONFIRMAR_SE_VERDE = "auto_confirmar_se_verde", "Confirmar se o OCR estiver verde"

    condominio = models.OneToOneField(
        Condominio, on_delete=models.CASCADE, related_name="configuracao"
    )
    antecedencia_minima_horas = models.PositiveSmallIntegerField(default=48)
    antecedencia_maxima_dias = models.PositiveSmallIntegerField(default=90)
    prazo_analise_horas = models.PositiveSmallIntegerField(default=24)
    politica_prazo_analise = models.CharField(
        max_length=30, choices=PoliticaPrazo.choices, default=PoliticaPrazo.MANTER
    )
    horas_para_reenvio = models.PositiveSmallIntegerField(default=12)
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
    pix_beneficiario = models.CharField(max_length=25, blank=True)
    pix_cidade = models.CharField(max_length=15, blank=True)

    whatsapp_url = models.URLField(
        blank=True, help_text="Link completo do WhatsApp, por exemplo https://wa.me/5511999999999."
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
