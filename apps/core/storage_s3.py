from django.conf import settings
from storages.backends.s3 import S3Storage


class _BaseS3(S3Storage):
    default_acl = None
    file_overwrite = False
    querystring_auth = False


class ArmazenamentoPublico(_BaseS3):
    """Logos e fotos de espaços: bucket com leitura pública."""

    location = "media"

    @property
    def bucket_name(self):
        return settings.STORAGE_S3_BUCKET


class ArmazenamentoPrivado(_BaseS3):
    """Comprovantes: URLs assinadas e, idealmente, bucket sem acesso público."""

    location = "privado"
    querystring_auth = True

    @property
    def bucket_name(self):
        return settings.STORAGE_S3_PRIVATE_BUCKET or settings.STORAGE_S3_BUCKET
