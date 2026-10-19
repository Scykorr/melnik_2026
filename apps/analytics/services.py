from __future__ import annotations

from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone

from apps.analytics.formula import ContributionInput, FormulaParams, contribution, rolling_index
from apps.analytics.models import DailyMetric
from apps.documents.models import Document
from apps.events.models import Event


def _factors(event: Event) -> tuple[float, float]:
    links = [
        link
        for link in event.links.all()
        if link.document.deleted_at is None and link.document.processing_status != Document.ProcessingStatus.DELETED
    ]
    if not links:
        return 0.0, 0.0
    quality = sum(link.document.source.reliability_weight for link in links) / len(links)
    families = {link.document.checksum for link in links}
    novelty = len(families) / len(links)
    return max(0.0, min(1.0, quality)), max(0.0, min(1.0, novelty))


def _raw_for_day(events: list[Event], day: date, params: FormulaParams) -> tuple[float, list[dict]]:
    total = 0.0
    parts: list[dict] = []
    for event in events:
        occurred = timezone.localtime(event.occurred_at).date()
        age = (day - occurred).days
        quality, novelty = _factors(event)
        item = ContributionInput(
            event_id=event.pk,
            relevance=event.relevance_score,
            scale=event.scale_score,
            source_quality=quality,
            novelty=novelty,
            age_days=age,
        )
        part = contribution(item, params)
        if part <= 0:
            continue
        total += part
        parts.append({"id": event.pk, "title": event.title, "contribution": round(part, 4)})
    return total, parts


@transaction.atomic
def rebuild_region_metrics(region_id: int, start: date | None = None, end: date | None = None, params: FormulaParams | None = None) -> int:
    params = params or FormulaParams()
    today = timezone.localdate()
    end = end or today
    start = start or (end - timedelta(days=89))
    events = list(
        Event.objects.filter(region_id=region_id, status=Event.Status.CONFIRMED, occurred_at__date__lte=end)
        .select_related("topic")
        .prefetch_related("links__document__source")
    )
    occurring: dict[date, list[str]] = {}
    for event in Event.objects.filter(region_id=region_id, occurred_at__date__gte=start, occurred_at__date__lte=end):
        occurring.setdefault(timezone.localtime(event.occurred_at).date(), []).append(event.status)
    lookback = start - timedelta(days=params.history_window_days)
    raw_by_day: dict[date, float] = {}
    parts_by_day: dict[date, list[dict]] = {}
    cursor = lookback
    while cursor <= end:
        raw, parts = _raw_for_day(events, cursor, params)
        raw_by_day[cursor] = raw
        parts_by_day[cursor] = parts
        cursor += timedelta(days=1)
    saved = 0
    cursor = start
    while cursor <= end:
        history = [raw_by_day[cursor - timedelta(days=offset)] for offset in range(params.history_window_days, 0, -1)]
        value, status = rolling_index(raw_by_day[cursor], history, params)
        statuses = occurring.get(cursor, [])
        confirmed_count = sum(1 for item in statuses if item == Event.Status.CONFIRMED)
        reviewable = [item for item in statuses if item != Event.Status.ARCHIVED]
        coverage = (confirmed_count / len(reviewable)) if reviewable else 1.0
        source_ids = set()
        for event in events:
            if timezone.localtime(event.occurred_at).date() != cursor:
                continue
            for link in event.links.all():
                if link.document.deleted_at is None:
                    source_ids.add(link.document.source_id)
        low_coverage = len(source_ids) < 2 or coverage < 0.5
        DailyMetric.objects.update_or_create(
            region_id=region_id,
            date=cursor,
            method_version=params.version,
            defaults={
                "index_value": value,
                "event_count": confirmed_count,
                "independent_source_count": len(source_ids),
                "review_coverage": round(coverage, 3),
                "components_json": {
                    "status": status,
                    "raw_sum": round(raw_by_day[cursor], 6),
                    "formula": params.version,
                    "window_days": params.history_window_days,
                    "events": parts_by_day[cursor],
                    "warning": "Индекс описывает открытый информационный поток, а не взгляды каждого жителя.",
                    "low_coverage": low_coverage,
                },
            },
        )
        saved += 1
        cursor += timedelta(days=1)
    return saved
