import uuid
from datetime import timedelta

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from apps.core.models import Condominio


def expiracao_padrao():
    return timezone.now() + timedelta(days=7)


class Usuario(AbstractUser):
    telefone = models.CharField(max_length=20, blank=True)
    email_confirmado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "usuário"
        verbose_name_plural = "usuários"

    def __str__(self) -> str:
        return self.get_full_name() or self.username


class Unidade(models.Model):
    condominio = models.ForeignKey(
        Condominio, on_delete=models.CASCADE, related_name="unidades"
    )
    bloco = models.CharField(max_length=20, blank=True)
    numero = models.CharField(max_length=20)
    administrativa = models.BooleanField(
        default=False,
        help_text="Unidade técnica do síndico/administradora; não conta como lote.",
    )
    limite_reservas_mes = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Reservas por mês deste lote. Vazio usa o limite do condomínio; 0 é ilimitado.",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["bloco", "numero"]
        constraints = [
            models.UniqueConstraint(
                fields=["condominio", "bloco", "numero"], name="unidade_unica_por_condominio"
            )
        ]
        verbose_name = "unidade"
        verbose_name_plural = "unidades"

    @property
    def rotulo(self) -> str:
        if self.bloco:
            return f"Bloco {self.bloco} - {self.numero}"
        return f"Unidade {self.numero}"

    def __str__(self) -> str:
        return f"{self.condominio.nome} · {self.rotulo}"


class VinculoUnidade(models.Model):
    class Papel(models.TextChoices):
        MORADOR = "morador", "Morador"
        SINDICO = "sindico", "Síndico"
        ADMINISTRADORA = "administradora", "Administradora"

    usuario = models.ForeignKey(
        Usuario, on_delete=models.CASCADE, related_name="vinculos"
    )
    unidade = models.ForeignKey(
        Unidade, on_delete=models.CASCADE, related_name="vinculos"
    )
    papel = models.CharField(max_length=20, choices=Papel.choices, default=Papel.MORADOR)
    ativo = models.BooleanField(default=True)
    bloqueio_reservas = models.BooleanField(
        default=False,
        verbose_name="bloqueado para reservas",
        help_text="Este morador não pode reservar nem entrar na lista de espera.",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["unidade__bloco", "unidade__numero"]
        constraints = [
            models.UniqueConstraint(
                fields=["usuario", "unidade", "papel"], name="vinculo_unico_por_papel"
            )
        ]
        verbose_name = "vínculo com unidade"
        verbose_name_plural = "vínculos com unidades"

    def __str__(self) -> str:
        return f"{self.usuario} · {self.unidade.rotulo} · {self.get_papel_display()}"


class Convite(models.Model):
    condominio = models.ForeignKey(
        Condominio, on_delete=models.CASCADE, related_name="convites"
    )
    unidade = models.ForeignKey(Unidade, on_delete=models.CASCADE, related_name="convites")
    papel = models.CharField(
        max_length=20,
        choices=VinculoUnidade.Papel.choices,
        default=VinculoUnidade.Papel.MORADOR,
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    criado_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="convites_criados",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    expira_em = models.DateTimeField(default=expiracao_padrao)
    usado_em = models.DateTimeField(null=True, blank=True)
    usado_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="convites_usados",
    )

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "convite"
        verbose_name_plural = "convites"

    def __str__(self) -> str:
        return f"{self.unidade.rotulo} · {self.get_papel_display()}"

    @property
    def valido(self) -> bool:
        return self.usado_em is None and timezone.now() < self.expira_em
