from django.core.management.base import BaseCommand, CommandError

from apps.common.exceptions import EvaluationError
from apps.experiments.calculations import evaluate_dedup


class Command(BaseCommand):
    help = "Считает метрики дедупликации только по загруженному эталону."

    def add_arguments(self, parser):
        parser.add_argument("--dataset", required=True)
        parser.add_argument("--method", default="tfidf")
        parser.add_argument("--split", default="test")
        parser.add_argument("--threshold", type=float, default=0.55)

    def handle(self, *args, **options):
        try:
            run = evaluate_dedup(
                dataset=options["dataset"],
                method=options["method"],
                split=options["split"],
                threshold=options["threshold"],
            )
        except EvaluationError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            f"method={run.method} split={run.split} tp={run.true_positive} fp={run.false_positive} "
            f"fn={run.false_negative} f1={run.f1} unreliable={run.unreliable}"
        )
        if run.warning:
            self.stdout.write(run.warning)
