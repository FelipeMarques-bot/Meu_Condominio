import calendar
import hashlib
import hmac
import ipaddress
import re
from datetime import date, timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from .models import Condominio


def ip_do_request(request) -> str:
    encaminhado = request.META.get("HTTP_X_FORWARDED_FOR", "")
    candidatos = [parte.strip() for parte in encaminhado.split(",") if parte.strip()]
    candidatos.append(request.META.get("REMOTE_ADDR", ""))
    for candidato in candidatos:
        try:
            endereco = ipaddress.ip_address(candidato)
        except ValueError:
            continue
        if isinstance(endereco, ipaddress.IPv6Address):
            rede = ipaddress.ip_network(f"{endereco}/64", strict=False)
            return str(rede.network_address)
        return str(endereco)
    return ""


def _hash(valor: str) -> str:
    if not valor:
        return ""
    chave = f"{settings.SECRET_KEY}:trial".encode()
    return hmac.new(chave, valor.encode(), hashlib.sha256).hexdigest()


def hash_ip(ip: str) -> str:
    return _hash(f"ip:{ip}")


def hash_dispositivo(valor: str) -> str:
    valor = (valor or "").strip()[:512]
    return _hash(f"dispositivo:{valor}") if valor else ""


def normalizar_telefone(telefone: str) -> str:
    return re.sub(r"\D", "", telefone or "")


def normalizar_email(email: str) -> str:
    email = (email or "").strip().lower()
    if "@" not in email:
        return email
    local, dominio = email.rsplit("@", 1)
    local = local.split("+", 1)[0]
    if dominio in {"gmail.com", "googlemail.com"}:
        local = local.replace(".", "")
        dominio = "gmail.com"
    return f"{local}@{dominio}"


def hashes_do_cadastro(
    request,
    telefone: str = "",
    email: str = "",
    dispositivo: str = "",
) -> dict:
    telefone_digitos = normalizar_telefone(telefone)
    email_normalizado = normalizar_email(email)
    dispositivo = (dispositivo or "").strip()[:512]
    return {
        "trial_ip_hash": hash_ip(ip_do_request(request)),
        "trial_telefone_hash": (
            _hash(f"tel:{telefone_digitos}") if telefone_digitos else ""
        ),
        "trial_email_hash": (
            _hash(f"email:{email_normalizado}") if email_normalizado else ""
        ),
        "trial_dispositivo_hash": hash_dispositivo(dispositivo),
    }


def adicionar_meses(base: date, meses: int = 1) -> date:
    indice = base.month - 1 + meses
    ano = base.year + indice // 12
    mes = indice % 12 + 1
    dia = min(base.day, calendar.monthrange(ano, mes)[1])
    return date(ano, mes, dia)


def proximo_vencimento(dia: int, base: date | None = None) -> date:
    dia = max(1, min(28, int(dia)))
    base = base or timezone.localdate()
    referencia = adicionar_meses(base, 1)
    return referencia.replace(day=dia)


def renovar_vencimento(condominio, dia: int | None = None) -> date:
    dia = max(1, min(28, int(dia or condominio.dia_vencimento or 1)))
    hoje = timezone.localdate()
    base = hoje
    if condominio.vencimento_em and condominio.vencimento_em >= hoje:
        base = condominio.vencimento_em
    return proximo_vencimento(dia, base)


def iniciar_trial(condominio, dias: int | None = None) -> None:
    dias = dias or int(getattr(settings, "TRIAL_DIAS", 14))
    fim = timezone.now() + timedelta(days=dias)
    condominio.trial_ate = fim
    condominio.vencimento_em = timezone.localtime(fim).date()
    condominio.dia_vencimento = min(condominio.vencimento_em.day, 28)
    condominio.save(
        update_fields=["trial_ate", "vencimento_em", "dia_vencimento"]
    )


def trial_ja_usado(hashes: dict) -> bool:
    dias = int(getattr(settings, "TRIAL_JANELA_DIAS", 30))
    desde = timezone.now() - timedelta(days=dias)
    condicao = Q()
    for campo in (
        "trial_ip_hash",
        "trial_telefone_hash",
        "trial_email_hash",
        "trial_dispositivo_hash",
    ):
        valor = hashes.get(campo)
        if valor:
            condicao |= Q(**{campo: valor})
    if not condicao:
        return False
    return Condominio.objects.filter(criado_em__gte=desde).filter(condicao).exists()
