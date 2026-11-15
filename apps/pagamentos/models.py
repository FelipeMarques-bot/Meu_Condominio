from django.db import models

from apps.core.models import Condominio


class EventoPix(models.Model):
    condominio = models.ForeignKey(
        Condominio, on_delete=models.CASCADE, related_name="eventos_pix"
    )
    gateway = models.CharField(max_length=20, default="abacatepay")
    evento_id = models.CharField(max_length=120)
    tipo = models.CharField(max_length=60, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    processado = models.BooleanField(default=False)
    detalhe = models.TextField(blank=True)
    recebido_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recebido_em"]
        constraints = [
            models.UniqueConstraint(
                fields=["condominio", "evento_id"], name="eventopix_unico_por_condominio"
            )
        ]
        verbose_name = "evento de Pix"
        verbose_name_plural = "eventos de Pix"

    def __str__(self) -> str:
        return f"{self.tipo or 'evento'} · {self.condominio.slug}"
