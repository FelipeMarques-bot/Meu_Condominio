from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class ArmazenamentoPrivadoLocal(FileSystemStorage):
    """Guarda arquivos fora da MEDIA_URL: só são servidos por view com permissão."""

    def __init__(self):
        super().__init__(base_url=None)

    @property
    def base_url(self):
        return None

    @property
    def location(self):
        return str(Path(settings.MEDIA_ROOT) / "privado")


def armazenamento_privado():
    if getattr(settings, "STORAGE_S3_ATIVO", False):
        from .storage_s3 import ArmazenamentoPrivado as ArmazenamentoPrivadoS3

        return ArmazenamentoPrivadoS3()
    return ArmazenamentoPrivadoLocal()
