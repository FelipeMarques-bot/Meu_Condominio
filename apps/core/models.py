from django.core.exceptions import ValidationError
from django.db import models


class Condominio(models.Model):
    nome = models.CharField(max_length=120)
    slug = models.SlugField(max_length=60, unique=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "condomínio"
        verbose_name_plural = "condomínios"

    def __str__(self) -> str:
        return self.nome

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
