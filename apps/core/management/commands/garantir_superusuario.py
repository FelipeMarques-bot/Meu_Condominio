import os

from django.core.management.base import BaseCommand, CommandError

from apps.usuarios.models import Usuario

TAMANHO_MINIMO_SENHA = 12


def _env(*nomes: str) -> str:
    for nome in nomes:
        valor = os.environ.get(nome)
        if valor:
            return valor.strip()
    return ""


class Command(BaseCommand):
    help = (
        "Cria o superusuário da plataforma a partir das variáveis de ambiente "
        "DJANGO_SUPERUSER_USERNAME, DJANGO_SUPERUSER_EMAIL e "
        "DJANGO_SUPERUSER_PASSWORD. Não faz nada se elas não estiverem definidas."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--atualizar-senha",
            action="store_true",
            help="Se o usuário já existir, redefine a senha com a variável de ambiente.",
        )

    def handle(self, *args, **opcoes):
        username = _env("DJANGO_SUPERUSER_USERNAME", "SUPERUSER_USERNAME")
        email = _env("DJANGO_SUPERUSER_EMAIL", "SUPERUSER_EMAIL")
        senha = _env("DJANGO_SUPERUSER_PASSWORD", "SUPERUSER_PASSWORD")

        if not username and not senha:
            self.stdout.write(
                "Superusuário ignorado: defina DJANGO_SUPERUSER_USERNAME e "
                "DJANGO_SUPERUSER_PASSWORD no ambiente."
            )
            return

        if not username or not senha:
            raise CommandError(
                "Defina as duas variáveis: DJANGO_SUPERUSER_USERNAME e "
                "DJANGO_SUPERUSER_PASSWORD."
            )

        if len(senha) < TAMANHO_MINIMO_SENHA:
            raise CommandError(
                f"A senha do superusuário precisa ter pelo menos "
                f"{TAMANHO_MINIMO_SENHA} caracteres."
            )

        usuario = Usuario.objects.filter(username__iexact=username).first()
        if usuario is None:
            Usuario.objects.create_superuser(
                username=username, email=email, password=senha
            )
            self.stdout.write(self.style.SUCCESS(f"Superusuário '{username}' criado."))
            return

        usuario.set_password(senha)
        usuario.is_staff = True
        usuario.is_superuser = True
        if email:
            usuario.email = email
        usuario.save(update_fields=["password", "is_staff", "is_superuser", "email"])
        self.stdout.write(
            self.style.SUCCESS(
                f"Superusuário '{username}' sincronizado com as variáveis de ambiente."
            )
        )
