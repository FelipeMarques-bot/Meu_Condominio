from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class ArmazenamentoPrivado(FileSystemStorage):
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
    return ArmazenamentoPrivado()
