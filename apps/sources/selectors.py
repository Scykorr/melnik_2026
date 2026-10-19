from __future__ import annotations

from datetime import timedelta

from django.db.models import Count
from django.utils import timezone

from apps.sources.models import Source


def source_health() -> list[dict]:
    now = timezone.now()
    rows = []
    for source in Source.objects.select_related("region_scope").annotate(doc_count=Count("documents")):
        docs = source.documents
        week = docs.filter(fetched_at__gte=now - timedelta(days=7)).count()
        prev = docs.filter(fetched_at__gte=now - timedelta(days=14), fetched_at__lt=now - timedelta(days=7)).count()
        total = docs.count()
        without_date = docs.filter(published_at__isnull=True).count()
        missed = 0
        if source.is_active and source.last_success_at:
            interval = timedelta(minutes=source.poll_interval)
            lag = now - source.last_success_at
            if interval.total_seconds() > 0 and lag > interval:
                missed = int(lag / interval) - 1
        latest_job = source.jobs.order_by("-created_at").first()
        rows.append(
            {
                "source": source,
                "documents": total,
                "week": week,
                "previous_week": prev,
                "coverage_drop": prev > 0 and week < prev,
                "without_date": without_date,
                "without_date_share": (without_date / total) if total else 0,
                "missed_intervals": max(missed, 0),
                "queue_status": latest_job.get_status_display() if latest_job else "нет заданий",
                "last_error": source.last_error,
            }
        )
    return rows
