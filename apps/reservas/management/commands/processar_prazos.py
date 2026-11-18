from django.core.management.base import BaseCommand

from apps.reservas.prazos import processar_prazos


class Command(BaseCommand):
    help = (
        "Libera reservas sem comprovante, avisa sobre prazos de análise vencidos "
        "e envia lembretes das reservas do dia seguinte."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dias-lembrete",
            type=int,
            default=1,
            help="Antecedência em dias do lembrete de reserva (padrão: 1).",
        )

    def handle(self, *args, **options):
        resumo = processar_prazos(options["dias_lembrete"])
        self.stdout.write(
            "Reservas expiradas: {expiradas} · Prazos alertados: {prazos_vencidos} "
            "· Lembretes: {lembretes}".format(**resumo)
        )
