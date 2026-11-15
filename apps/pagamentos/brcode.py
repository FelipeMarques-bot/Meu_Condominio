import base64
import io
import unicodedata
from decimal import Decimal

import qrcode


def _campo(identificador: str, valor: str) -> str:
    return f"{identificador}{len(valor):02d}{valor}"


def _texto(valor: str, limite: int) -> str:
    normalizado = (
        unicodedata.normalize("NFKD", valor or "")
        .encode("ascii", "ignore")
        .decode("ascii")
        .upper()
    )
    return normalizado[:limite]


def crc16(payload: str) -> str:
    crc = 0xFFFF
    for byte in payload.encode("utf-8"):
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def gerar_payload(
    chave: str, nome: str, cidade: str, valor: Decimal | str
) -> str:
    chave = (chave or "").strip()
    if not chave:
        raise ValueError("Chave Pix não configurada.")

    nome = _texto(nome, 25) or "CONDOMINIO"
    cidade = _texto(cidade, 15) or "BRASIL"
    valor_texto = f"{Decimal(valor):.2f}"

    conta = _campo("00", "br.gov.bcb.pix") + _campo("01", chave)
    payload = (
        "000201"
        + _campo("26", conta)
        + "52040000"
        + "5303986"
        + _campo("54", valor_texto)
        + "5802BR"
        + _campo("59", nome)
        + _campo("60", cidade)
        + "62070503***"
        + "6304"
    )
    return payload + crc16(payload)


def gerar_qr_data_uri(payload: str) -> str:
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    imagem = qr.make_image(fill_color="#0C1B1F", back_color="white")

    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG")
    codificado = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{codificado}"
