from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.core.models import Condominio
from apps.core.tenancy import TenantManager
from apps.usuarios.models import Unidade, Usuario


class Local(models.Model):
    class Categoria(models.TextChoices):
        SALAO = "salao", "Salão de festas"
        QUIOSQUE = "quiosque", "Quiosque"
        CHURRASQUEIRA = "churrasqueira", "Churrasqueira"
        QUADRA = "quadra", "Quadra"
        PISCINA = "piscina", "Piscina"
        OUTRO = "outro", "Outro"

    condominio = models.ForeignKey(Condominio, on_delete=models.CASCADE, related_name="locais")
    nome = models.CharField(max_length=100)
    slug = models.SlugField(max_length=60)
    categoria = models.CharField(
        max_length=20, choices=Categoria.choices, default=Categoria.OUTRO
    )
    descricao = models.TextField(blank=True)
    capacidade = models.PositiveSmallIntegerField(default=0)
    valor = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    foto = models.ImageField(upload_to="locais/", blank=True)
    ativo = models.BooleanField(default=True)
    ordem = models.PositiveSmallIntegerField(default=0)
    criado_em = models.DateTimeField(auto_now_add=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ["ordem", "nome"]
        constraints = [
            models.UniqueConstraint(
                fields=["condominio", "slug"], name="local_unico_por_condominio"
            )
        ]
        verbose_name = "local"
        verbose_name_plural = "locais"

    def __str__(self) -> str:
        return f"{self.nome} · {self.condominio.nome}"

    @property
    def valor_formatado(self) -> str:
        return f"R$ {self.valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


class Reserva(models.Model):
    class Status(models.TextChoices):
        AGUARDANDO_COMPROVANTE = "aguardando_comprovante", "Aguardando comprovante"
        EM_ANALISE = "em_analise", "Em análise"
        CONFIRMADA = "confirmada", "Confirmada"
        REJEITADA = "rejeitada", "Rejeitada"
        EXPIRADA = "expirada", "Expirada"
        CANCELADA = "cancelada", "Cancelada"

    condominio = models.ForeignKey(
        Condominio, on_delete=models.CASCADE, related_name="reservas"
    )
    local = models.ForeignKey(Local, on_delete=models.PROTECT, related_name="reservas")
    unidade = models.ForeignKey(
        Unidade, on_delete=models.PROTECT, related_name="reservas"
    )
    solicitante = models.ForeignKey(
        Usuario, on_delete=models.SET_NULL, null=True, blank=True, related_name="reservas"
    )
    inicio = models.DateTimeField()
    fim = models.DateTimeField()
    valor = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(
        max_length=30, choices=Status.choices, default=Status.AGUARDANDO_COMPROVANTE
    )
    comprovante = models.FileField(upload_to="comprovantes/%Y/%m/", blank=True)
    comprovante_enviado_em = models.DateTimeField(null=True, blank=True)
    expira_em = models.DateTimeField(null=True, blank=True)
    prazo_analise_em = models.DateTimeField(null=True, blank=True)
    confirmado_em = models.DateTimeField(null=True, blank=True)
    codigo_checkin = models.CharField(max_length=8, blank=True)
    motivo_rejeicao = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ["-inicio"]
        constraints = [
            models.CheckConstraint(condition=Q(fim__gt=F("inicio")), name="reserva_fim_apos_inicio")
        ]
        indexes = [
            models.Index(fields=["condominio", "inicio"], name="reserva_condominio_inicio"),
            models.Index(fields=["local", "inicio"], name="reserva_local_inicio"),
        ]
        verbose_name = "reserva"
        verbose_name_plural = "reservas"

    def __str__(self) -> str:
        return f"{self.local.nome} · {self.inicio:%d/%m/%Y %H:%M}"

    def clean(self) -> None:
        errors = {}
        if self.local_id and self.local.condominio_id != self.condominio_id:
            errors["local"] = "O local pertence a outro condomínio."
        if self.unidade_id and self.unidade.condominio_id != self.condominio_id:
            errors["unidade"] = "A unidade pertence a outro condomínio."
        if self.inicio and self.fim and self.fim <= self.inicio:
            errors["fim"] = "O término deve ser posterior ao início."
        if errors:
            raise ValidationError(errors)

    @property
    def prazo_vencido(self) -> bool:
        return bool(self.prazo_analise_em and timezone.now() > self.prazo_analise_em)

    @property
    def hold_vencido(self) -> bool:
        return bool(
            self.status == self.Status.AGUARDANDO_COMPROVANTE
            and self.expira_em
            and timezone.now() > self.expira_em
        )

    @property
    def pode_receber_comprovante(self) -> bool:
        return self.status in {
            self.Status.AGUARDANDO_COMPROVANTE,
            self.Status.REJEITADA,
        }
