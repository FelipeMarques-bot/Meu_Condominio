from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.core.models import Condominio, ConfiguracaoCondominio
from apps.reservas.models import Local
from apps.usuarios.models import Unidade

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

        acao = "criado" if criado else "atualizado"
        endereco = f"/c/{condominio.slug}/agenda/"
        self.stdout.write(
            self.style.SUCCESS(f"Condomínio de demonstração {acao}: {condominio.nome} ({endereco})")
        )
