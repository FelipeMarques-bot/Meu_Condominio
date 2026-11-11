from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.core.models import Condominio


class Usuario(AbstractUser):
    telefone = models.CharField(max_length=20, blank=True)

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
