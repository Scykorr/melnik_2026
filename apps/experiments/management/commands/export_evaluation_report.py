from pathlib import Path

from django.core.management.base import BaseCommand

from apps.experiments.calculations import labor_summary
from apps.experiments.models import EvaluationRun


class Command(BaseCommand):
    help = "Собирает отчёт испытаний из реальных записей, без выдуманных метрик."

    def add_arguments(self, parser):
        parser.add_argument("--output", default="media/evaluation_report.md")

    def handle(self, *args, **options):
        summary = labor_summary()
        lines = [
            "# Отчёт испытаний",
            "",
            "Значения ниже берутся только из сохранённых сессий и прогонов. Пустые поля не заполняются догадкой.",
            "",
            "## Трудоёмкость",
            "",
            f"- Статус: {summary['status']}",
            f"- Пар: {summary['pairs']}",
            f"- Медиана K_T: {summary['median'] if summary['median'] is not None else 'не измерено'}",
            f"- Экономия, часы: {summary['saved_hours'] if summary['saved_hours'] is not None else 'не измерено'}",
            "",
            "## Качество дедупликации",
            "",
        ]
        runs = EvaluationRun.objects.filter(dataset_kind="external", unreliable=False)
        if not runs.exists():
            lines.append("F1, Precision и Recall: не измерено.")
        else:
            lines.append("| Дата | Метод | Split | Выборка | Precision | Recall | F1 |")
            lines.append("| --- | --- | --- | --- | --- | --- | --- |")
            for run in runs:
                lines.append(
                    f"| {run.created_at.date()} | {run.method} | {run.split} | {run.sample_size} | {run.precision} | {run.recall} | {run.f1} |"
                )
        path = Path(options["output"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines), encoding="utf-8")
        self.stdout.write(str(path))
