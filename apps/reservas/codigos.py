import secrets

from .models import Reserva

ALFABETO_CHECKIN = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def gerar_codigo_checkin(condominio) -> str:
    for _ in range(20):
        codigo = "".join(secrets.choice(ALFABETO_CHECKIN) for _ in range(6))
        if not Reserva.all_objects.filter(
            condominio=condominio, codigo_checkin=codigo
        ).exists():
            return codigo
    return secrets.token_hex(3).upper()
