import base64
import hashlib
import hmac
import json
import urllib.error
import urllib.request
from datetime import timedelta

from django.utils import timezone
from django.utils.dateparse import parse_datetime

BASE_URL = "https://api.abacatepay.com/v2"

CHAVE_PUBLICA_WEBHOOK = (
    "t9dXRhHHo3yDEj5pVDYz0frf7q6bMKyMRmxxCPIPp3RCplBfXRxqlC6ZpiWmOqj4L63qEaeUOtrCI8P0"
    "VMUgo6iIga2ri9ogaHFs0WIIywSMg0q7RmBfybe1E5XJcfC4IW3alNqym0tXoAKkzvfEjZxV6bE0oG2zJr"
    "NNYmUCKZyV0KZ3JS8Votf9EAWWYdiDkMkpbMdPggfh1EqHlVkMiTady6jOR3hyzGEHrIz2Ret0xHKMbiq"
    "kr9HS1JhNHDX9"
)

EXPIRACAO_SEGUNDOS = 2 * 60 * 60


class ErroAbacatePay(Exception):
    pass


def _abrir(requisicao, timeout):
    # BASE_URL é https fixa; o caminho vem do código, nunca do usuário.
    return urllib.request.urlopen(requisicao, timeout=timeout)  # nosec B310


def _mensagem_de_erro(exc: urllib.error.HTTPError) -> str:
    try:
        corpo = json.loads(exc.read().decode("utf-8"))
    except (ValueError, OSError):
        return f"A AbacatePay recusou a cobrança (HTTP {exc.code})."
    erro = corpo.get("error")
    if isinstance(erro, dict):
        erro = erro.get("message") or erro.get("code")
    if erro:
        return str(erro)
    return f"A AbacatePay recusou a cobrança (HTTP {exc.code})."


def _post_json(caminho: str, api_key: str, dados: dict, timeout: int = 15) -> dict:
    corpo = json.dumps(dados).encode("utf-8")
    requisicao = urllib.request.Request(
        f"{BASE_URL}{caminho}",
        data=corpo,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with _abrir(requisicao, timeout) as resposta:
            texto = resposta.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise ErroAbacatePay(_mensagem_de_erro(exc)) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ErroAbacatePay("Não foi possível falar com a AbacatePay agora.") from exc

    try:
        envelope = json.loads(texto)
    except ValueError as exc:
        raise ErroAbacatePay("Resposta inesperada da AbacatePay.") from exc

    if not envelope.get("success") or envelope.get("error"):
        raise ErroAbacatePay("A AbacatePay recusou a cobrança.")
    return envelope.get("data") or {}


def criar_cobranca_pix(
    *,
    api_key: str,
    valor_centavos: int,
    descricao: str,
    external_id: str,
    expires_in: int = EXPIRACAO_SEGUNDOS,
) -> dict:
    dados = _post_json(
        "/transparents/create",
        api_key,
        {
            "method": "PIX",
            "data": {
                "amount": int(valor_centavos),
                "description": (descricao or "")[:140],
                "externalId": str(external_id),
                "expiresIn": int(expires_in),
            },
        },
    )
    brcode = dados.get("brCode")
    if not brcode:
        raise ErroAbacatePay("A AbacatePay não devolveu o código Pix.")

    expira_em = None
    if dados.get("expiresAt"):
        expira_em = parse_datetime(str(dados["expiresAt"]))
    if expira_em is None:
        expira_em = timezone.now() + timedelta(seconds=expires_in)

    brcode_base64 = dados.get("brCodeBase64") or ""
    if brcode_base64 and not brcode_base64.startswith("data:"):
        brcode_base64 = f"data:image/png;base64,{brcode_base64}"

    return {
        "id": str(dados.get("id") or ""),
        "brcode": brcode,
        "brcode_base64": brcode_base64,
        "expira_em": expira_em,
        "status": dados.get("status") or "PENDING",
        "dev_mode": bool(dados.get("devMode")),
    }


def assinatura_valida(corpo: bytes, assinatura: str) -> bool:
    if not assinatura:
        return False
    esperado = base64.b64encode(
        hmac.new(CHAVE_PUBLICA_WEBHOOK.encode("utf-8"), corpo, hashlib.sha256).digest()
    ).decode("ascii")
    return hmac.compare_digest(esperado, assinatura.strip())
