from datetime import date

from django.core.management.base import BaseCommand, CommandError

from apps.analytics.models import DailyMetric
from apps.audit.services import write_audit
from apps.events.models import Assessment
from apps.reports.models import Report


class Command(BaseCommand):
    help = "Удаляет производные агрегаты старше даты. Текст публикаций в журнал не копируется."

    def add_arguments(self, parser):
        parser.add_argument("--before", required=True)
        parser.add_argument("--reason", required=True)

    def handle(self, *args, **options):
        if not options["reason"].strip():
            raise CommandError("Нужно основание")
        limit = date.fromisoformat(options["before"])
        metrics = DailyMetric.objects.filter(date__lt=limit).count()
        DailyMetric.objects.filter(date__lt=limit).delete()
        assessments = Assessment.objects.filter(created_at__date__lt=limit).count()
        Assessment.objects.filter(created_at__date__lt=limit).delete()
        drafts = Report.objects.filter(status=Report.Status.DRAFT, created_at__date__lt=limit).count()
        Report.objects.filter(status=Report.Status.DRAFT, created_at__date__lt=limit).delete()
        write_audit(
            actor=None,
            action="derived_purged",
            object_type="retention",
            object_id=limit.isoformat(),
            before={"metrics": metrics, "assessments": assessments, "drafts": drafts},
            after={"status": "purged"},
            reason=options["reason"],
        )
        self.stdout.write(self.style.SUCCESS("Производные данные удалены"))
