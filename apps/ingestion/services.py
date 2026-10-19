from __future__ import annotations

from django.utils import timezone

from apps.audit.services import write_audit
from apps.documents.services import ingest_payload
from apps.ingestion.adapters import ADAPTERS
from apps.ingestion.errors import TemporaryIngestError
from apps.ingestion.models import IngestJob
from apps.sources.models import Source


def run_source_poll(source_id: int) -> IngestJob:
    source = Source.objects.get(pk=source_id)
    job = IngestJob.objects.create(source=source, status=IngestJob.Status.RUNNING, started_at=timezone.now())
    adapter = ADAPTERS.get(source.source_type)
    if adapter is None:
        job.status = IngestJob.Status.ERROR
        job.error_message = "Адаптер не зарегистрирован"
        job.finished_at = timezone.now()
        job.save()
        source.last_error = job.error_message
        source.save(update_fields=["last_error", "updated_at"])
        return job
    try:
        items = adapter.fetch(source)
        created = 0
        skipped = 0
        for item in items:
            _doc, was_created = ingest_payload(
                source=source,
                url=item.url,
                title=item.title,
                text=item.text,
                published_at=item.published_at,
                language=item.language,
                metadata=item.metadata,
                mime=item.mime,
            )
            if was_created:
                created += 1
            else:
                skipped += 1
        job.items_seen = len(items)
        job.items_created = created
        job.items_skipped = skipped
        job.status = IngestJob.Status.SUCCESS
        job.finished_at = timezone.now()
        job.save()
        source.last_success_at = timezone.now()
        source.last_error = ""
        if source.source_type == "official_api":
            source.last_error = ""
        source.save(update_fields=["last_success_at", "last_error", "updated_at"])
        write_audit(
            actor=None,
            action="source_polled",
            object_type="source",
            object_id=source.pk,
            after={"created": created, "skipped": skipped, "seen": len(items)},
        )
        return job
    except TemporaryIngestError:
        job.status = IngestJob.Status.ERROR
        job.error_message = "Временная ошибка, задание будет повторено"
        job.finished_at = timezone.now()
        job.save()
        source.last_error = job.error_message
        source.save(update_fields=["last_error", "updated_at"])
        raise
    except Exception as exc:
        message = str(exc)[:300] or "Ошибка загрузки"
        job.status = IngestJob.Status.ERROR
        job.error_message = message
        job.finished_at = timezone.now()
        job.save()
        source.last_error = message
        source.save(update_fields=["last_error", "updated_at"])
        return job
