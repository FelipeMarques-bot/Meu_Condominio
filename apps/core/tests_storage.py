from django.test import SimpleTestCase, override_settings

from .storage import ArmazenamentoPrivadoLocal, armazenamento_privado


class ArmazenamentoPrivadoTests(SimpleTestCase):
    def test_sem_s3_usa_disco_local(self):
        self.assertIsInstance(armazenamento_privado(), ArmazenamentoPrivadoLocal)

    @override_settings(
        STORAGE_S3_ATIVO=True,
        STORAGE_S3_BUCKET="bucket-publico",
        STORAGE_S3_PRIVATE_BUCKET="bucket-privado",
        AWS_ACCESS_KEY_ID="chave",
        AWS_SECRET_ACCESS_KEY="segredo",
        AWS_STORAGE_BUCKET_NAME="bucket-publico",
    )
    def test_com_s3_usa_bucket_privado_com_url_assinada(self):
        armazenamento = armazenamento_privado()

        self.assertEqual(armazenamento.bucket_name, "bucket-privado")
        self.assertTrue(armazenamento.querystring_auth)
        self.assertEqual(armazenamento.location, "privado")

    @override_settings(
        STORAGE_S3_ATIVO=True,
        STORAGE_S3_BUCKET="bucket-unico",
        STORAGE_S3_PRIVATE_BUCKET="",
        AWS_ACCESS_KEY_ID="chave",
        AWS_SECRET_ACCESS_KEY="segredo",
        AWS_STORAGE_BUCKET_NAME="bucket-unico",
    )
    def test_sem_bucket_privado_reaproveita_o_publico(self):
        self.assertEqual(armazenamento_privado().bucket_name, "bucket-unico")
