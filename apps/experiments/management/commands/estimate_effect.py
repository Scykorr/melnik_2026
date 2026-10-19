from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.experiments.calculations import economic_effect


class Command(BaseCommand):
    help = "Считает прогнозный экономический эффект. Это не фактический результат."

    def add_arguments(self, parser):
        parser.add_argument("--t0", type=Decimal, required=True)
        parser.add_argument("--t1", type=Decimal, required=True)
        parser.add_argument("--n", type=Decimal, required=True)
        parser.add_argument("--c", type=Decimal, required=True)
        parser.add_argument("--c-op", type=Decimal, required=True)
        parser.add_argument("--capex", type=Decimal)

    def handle(self, *args, **options):
        result = economic_effect(
            t0=options["t0"],
            t1=options["t1"],
            releases=options["n"],
            hourly=options["c"],
            operating=options["c_op"],
            capex=options["capex"],
        )
        self.stdout.write("ПРОГНОЗ, не фактический результат проекта")
        self.stdout.write(f"E={result['effect']} окупаемость={result['payback']}")
