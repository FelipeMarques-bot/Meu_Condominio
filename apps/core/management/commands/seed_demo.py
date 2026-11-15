from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.core.models import Condominio, ConfiguracaoCondominio
from apps.reservas.models import Local
from apps.usuarios.models import Unidade, Usuario, VinculoUnidade

LOCAIS = [
    {
        "nome": "Salão de Festas",
        "slug": "salao-de-festas",
        "categoria": Local.Categoria.SALAO,
        "descricao": "Salão com cozinha equipada, mesas e cadeiras para até 80 pessoas.",
        "capacidade": 80,
        "valor": Decimal("350.00"),
        "ordem": 1,
    },
    {
        "nome": "Quiosque Primavera",
        "slug": "quiosque-primavera",
        "categoria": Local.Categoria.QUIOSQUE,
        "descricao": "Quiosque coberto com churrasqueira, pia e vista para o jardim.",
        "capacidade": 30,
        "valor": Decimal("180.00"),
        "ordem": 2,
    },
    {
        "nome": "Churrasqueira do Lago",
        "slug": "churrasqueira-do-lago",
        "categoria": Local.Categoria.CHURRASQUEIRA,
        "descricao": "Área gourmet com bancada, freezer e acesso à área verde.",
        "capacidade": 20,
        "valor": Decimal("120.00"),
        "ordem": 3,
    },
    {
        "nome": "Quadra Poliesportiva",
        "slug": "quadra-poliesportiva",
        "categoria": Local.Categoria.QUADRA,
        "descricao": "Quadra coberta para futebol, vôlei e basquete.",
        "capacidade": 24,
        "valor": Decimal("80.00"),
        "ordem": 4,
    },
]


class Command(BaseCommand):
    help = "Cria um condomínio de demonstração com espaços e unidades."

    def add_arguments(self, parser):
        parser.add_argument("--slug", default="bela-vista")
        parser.add_argument("--nome", default="Condomínio Bela Vista")
        parser.add_argument(
            "--usuarios",
            action="store_true",
            help="Cria morador, síndico, administradora e dono da plataforma (senha demo1234).",
        )

    def handle(self, *args, **options):
        slug = options["slug"]
        nome = options["nome"]

        condominio, criado = Condominio.objects.get_or_create(
            slug=slug, defaults={"nome": nome}
        )
        ConfiguracaoCondominio.objects.get_or_create(condominio=condominio)

        for bloco, numero in [("A", "101"), ("A", "102"), ("B", "201")]:
            Unidade.objects.get_or_create(
                condominio=condominio, bloco=bloco, numero=numero
            )

        for dados in LOCAIS:
            Local.all_objects.get_or_create(
                condominio=condominio, slug=dados["slug"], defaults=dados
            )

        if options["usuarios"]:
            self._criar_usuarios(condominio)

        acao = "criado" if criado else "atualizado"
        endereco = f"/c/{condominio.slug}/agenda/"
        self.stdout.write(
            self.style.SUCCESS(f"Condomínio de demonstração {acao}: {condominio.nome} ({endereco})")
        )

    def _criar_usuarios(self, condominio):
        unidade = condominio.unidades.filter(bloco="A", numero="101").first()
        if unidade is None:
            unidade = Unidade.objects.create(
                condominio=condominio, bloco="A", numero="101"
            )

        combinacoes = [
            ("morador", "Morador Demo", VinculoUnidade.Papel.MORADOR),
            ("sindico", "Síndico Demo", VinculoUnidade.Papel.SINDICO),
            ("gestora", "Administradora Demo", VinculoUnidade.Papel.ADMINISTRADORA),
        ]

        for username, nome, papel in combinacoes:
            usuario, criado = Usuario.objects.get_or_create(
                username=username,
                defaults={"email": f"{username}@example.com", "first_name": nome},
            )
            if criado:
                usuario.set_password("demo1234")
                usuario.save(update_fields=["password"])
            VinculoUnidade.objects.get_or_create(
                usuario=usuario, unidade=unidade, papel=papel
            )

        if not Usuario.objects.filter(username="dono").exists():
            Usuario.objects.create_superuser(
                username="dono",
                email="dono@example.com",
                password="demo1234",
                first_name="Dono da Plataforma",
            )
