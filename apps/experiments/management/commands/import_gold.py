import csv
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.experiments.models import GoldDocumentLabel, GoldEventGroup

BANNED = {"author", "authors", "fio", "email", "phone", "person", "persons", "profile", "name", "passport"}
REQUIRED = {"document_uid", "relevance", "topic_code", "region_code", "event_group_id", "rules_version", "split", "status"}
OPTIONAL = {"text", "published_on", "dataset_kind"}


def assign_splits(labels: list[GoldDocumentLabel]) -> bool:
    groups: dict[str, list[GoldDocumentLabel]] = {}
    for label in labels:
        groups.setdefault(label.event_group_id or label.document_uid, []).append(label)
    ordered = sorted(groups.values(), key=lambda group: min(item.published_on or date.min for item in group))
    count = len(ordered)
    for index, group in enumerate(ordered):
        if count < 5:
            split = "test" if index == count - 1 else "train"
        elif index < int(count * 0.6):
            split = "train"
        elif index < int(count * 0.8):
            split = "validation"
        else:
            split = "test"
        for item in group:
            item.split = split
            item.save(update_fields=["split", "updated_at"])
    return count < 3


class Command(BaseCommand):
    help = "Импортирует эталонную разметку. Реальный корпус в git не хранится."

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--dataset", required=True)
        parser.add_argument("--kind", default="external", choices=["external", "synthetic"])

    def handle(self, *args, **options):
        path = Path(options["path"])
        if not path.exists():
            raise CommandError("Файл эталона не найден. Метрики не вычисляются.")
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = set(reader.fieldnames or [])
            if fields & BANNED:
                raise CommandError("В файле есть поля персональных профилей. Импорт остановлен.")
            missing = REQUIRED - fields
            if missing:
                raise CommandError(f"В эталоне нет колонок: {', '.join(sorted(missing))}")
            unknown = fields - REQUIRED - OPTIONAL
            if unknown:
                raise CommandError(f"Неизвестные колонки: {', '.join(sorted(unknown))}")
            rows = list(reader)
        if not rows:
            raise CommandError("Эталон пуст.")
        labels = []
        for row in rows:
            published = None
            if row.get("published_on"):
                published = date.fromisoformat(row["published_on"])
            label, _ = GoldDocumentLabel.objects.update_or_create(
                dataset=options["dataset"],
                document_uid=row["document_uid"],
                defaults={
                    "relevance": row["relevance"],
                    "topic_code": row["topic_code"],
                    "region_code": row["region_code"],
                    "event_group_id": row["event_group_id"],
                    "rules_version": row["rules_version"],
                    "split": row.get("split") or "",
                    "status": row.get("status") or "active",
                    "text": row.get("text") or "",
                    "published_on": published,
                    "dataset_kind": options["kind"],
                },
            )
            labels.append(label)
            if row["event_group_id"]:
                GoldEventGroup.objects.update_or_create(
                    dataset=options["dataset"],
                    event_group_id=row["event_group_id"],
                    defaults={"region_code": row["region_code"], "topic_code": row["topic_code"]},
                )
        if any(not item.split for item in labels):
            warning = assign_splits(labels)
            if warning:
                self.stdout.write("Мало групп для надёжного разбиения. Оценка будет ненадёжной.")
        self.stdout.write(self.style.SUCCESS(f"Импортировано записей: {len(labels)}"))
