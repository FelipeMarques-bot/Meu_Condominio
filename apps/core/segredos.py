import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet() -> Fernet:
    chave = os.environ.get("CHAVE_CRIPTOGRAFIA") or settings.SECRET_KEY
    resumo = hashlib.sha256(f"meu-condominio:{chave}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(resumo))


def criptografar(texto: str) -> str:
    if not texto:
        return ""
    return _fernet().encrypt(texto.encode("utf-8")).decode("ascii")


def descriptografar(token: str) -> str:
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""
