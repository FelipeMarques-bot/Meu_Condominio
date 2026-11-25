import logging
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from django.conf import settings

from .models import Reserva

logger = logging.getLogger(__name__)

REGEX_VALOR = re.compile(r"R\$\s*([\d.]*,\d{2})")
REGEX_DATA = re.compile(r"\b(\d{2})[/\-.](\d{2})[/\-.](\d{4})\b")
PALAVRAS_PAGAMENTO = (
    "pix",
    "comprovante",
    "pagamento",
    "pago",
    "transferência",
    "transferencia",
)


@dataclass(frozen=True)
class ResultadoOCR:
    situacao: str
    valor: Decimal | None = None
    data: date | None = None
    observacao: str = ""


def _texto_do_arquivo(arquivo) -> str:
    import pypdfium2 as pdfium
    import pytesseract
    from PIL import Image

    arquivo.seek(0)
    try:
        if (arquivo.name or "").lower().endswith(".pdf"):
            documento = pdfium.PdfDocument(arquivo.read())
            imagem = documento[0].render(scale=2).to_pil()
        else:
            imagem = Image.open(arquivo).convert("RGB")

        idioma = settings.OCR_IDIOMA
        try:
            return pytesseract.image_to_string(imagem, lang=idioma, timeout=settings.OCR_TIMEOUT)
        except pytesseract.TesseractError:
            if idioma == "eng":
                raise
            return pytesseract.image_to_string(imagem, lang="eng", timeout=settings.OCR_TIMEOUT)
    finally:
        arquivo.seek(0)


def _reais(valor: Decimal) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _extrair_valores(texto: str) -> list[Decimal]:
    valores = []
    for match in REGEX_VALOR.finditer(texto):
        try:
            valores.append(Decimal(match.group(1).replace(".", "").replace(",", ".")))
        except InvalidOperation:
            continue
    return valores


def _extrair_datas(texto: str) -> list[date]:
    datas = []
    for dia, mes, ano in REGEX_DATA.findall(texto):
        try:
            datas.append(date(int(ano), int(mes), int(dia)))
        except ValueError:
            continue
    return datas


def _classificar(texto: str, valor_esperado: Decimal, data_esperada: date) -> ResultadoOCR:
    situacoes = Reserva.OcrStatus
    if not texto.strip():
        return ResultadoOCR(
            situacoes.AMARELO,
            observacao="A leitura automática não encontrou texto. Confira o arquivo.",
        )

    valores = _extrair_valores(texto)
    if not valores:
        return ResultadoOCR(
            situacoes.AMARELO,
            observacao="Não foi possível identificar o valor pago. Confira o arquivo.",
        )

    valor = min(valores, key=lambda item: abs(item - valor_esperado))
    if abs(valor - valor_esperado) > Decimal("0.01"):
        return ResultadoOCR(
            situacoes.VERMELHO,
            valor=valor,
            observacao=(
                f"Valor lido {_reais(valor)} não confere com {_reais(valor_esperado)} da reserva."
            ),
        )

    datas = _extrair_datas(texto)
    if not datas:
        return ResultadoOCR(
            situacoes.AMARELO,
            valor=valor,
            observacao="O valor confere, mas a data do pagamento não foi identificada.",
        )

    data = min(datas, key=lambda item: abs((item - data_esperada).days))
    if abs((data - data_esperada).days) > 1:
        return ResultadoOCR(
            situacoes.VERMELHO,
            valor=valor,
            data=data,
            observacao=(
                f"Data lida {data:%d/%m/%Y} não confere com a reserva ({data_esperada:%d/%m/%Y})."
            ),
        )

    if not any(palavra in texto.lower() for palavra in PALAVRAS_PAGAMENTO):
        return ResultadoOCR(
            situacoes.AMARELO,
            valor=valor,
            data=data,
            observacao=(
                "Valor e data conferem, mas o texto não confirma que se trata "
                "de um comprovante de pagamento."
            ),
        )

    return ResultadoOCR(
        situacoes.VERDE,
        valor=valor,
        data=data,
        observacao="Valor, data e pagamento conferem com a reserva.",
    )


def analisar_comprovante(arquivo, valor_esperado: Decimal, data_esperada: date) -> ResultadoOCR:
    """Lê o comprovante e devolve uma classificação; nunca interrompe o envio."""
    if not settings.OCR_ATIVO:
        return ResultadoOCR(
            Reserva.OcrStatus.AMARELO,
            observacao="Leitura automática desativada. Confira o comprovante manualmente.",
        )

    try:
        texto = _texto_do_arquivo(arquivo)
    except Exception:
        logger.info("Não foi possível ler o comprovante com OCR.", exc_info=True)
        return ResultadoOCR(
            Reserva.OcrStatus.AMARELO,
            observacao="Leitura automática indisponível. Confira o comprovante manualmente.",
        )

    return _classificar(texto, valor_esperado, data_esperada)
