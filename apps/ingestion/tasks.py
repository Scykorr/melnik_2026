from __future__ import annotations

from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.ingestion.errors import TemporaryIngestError
from apps.ingestion.services import run_source_poll
from apps.sources.models import Source


@shared_task(
    bind=True,
    autoretry_for=(TemporaryIngestError,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=5,
)
def poll_source(self, source_id: int) -> int:
    job = run_source_poll(source_id)
    return job.pk


@shared_task
def poll_due_sources() -> int:
    now = timezone.now()
    queued = 0
    for source in Source.objects.filter(is_active=True):
        if source.last_success_at and now - source.last_success_at < timedelta(minutes=source.poll_interval):
            continue
        poll_source.delay(source.pk)
        queued += 1
    return queued
