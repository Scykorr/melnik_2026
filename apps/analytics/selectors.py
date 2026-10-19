from __future__ import annotations

from apps.analytics.models import DailyMetric
from apps.documents.models import Document
from apps.events.models import Event
from apps.sources.models import Source


def dashboard_payload(region, start, end) -> dict:
    if region is None:
        return {"empty": True, "metrics": [], "topics": [], "events": [], "index": None, "quality": {}}
    metrics = list(
        DailyMetric.objects.filter(region=region, date__gte=start, date__lte=end).order_by("date")
    )
    usable = [item for item in metrics if item.index_value is not None]
    latest = usable[-1] if usable else (metrics[-1] if metrics else None)
    previous = usable[-2] if len(usable) > 1 else None
    delta = None
    if latest and previous and latest.index_value is not None and previous.index_value is not None:
        delta = round(latest.index_value - previous.index_value, 2)
    confirmed = Event.objects.filter(
        region=region,
        status=Event.Status.CONFIRMED,
        occurred_at__date__gte=start,
        occurred_at__date__lte=end,
    ).select_related("topic").prefetch_related("links__document")
    source_ids = {
        link.document.source_id
        for event in confirmed
        for link in event.links.all()
        if link.document.deleted_at is None
    }
    topic_map: dict[str, int] = {}
    for event in confirmed:
        topic_map[event.topic.name] = topic_map.get(event.topic.name, 0) + 1
    topics = [{"name": name, "count": count} for name, count in sorted(topic_map.items(), key=lambda item: -item[1])]
    all_events = Event.objects.filter(region=region, occurred_at__date__gte=start, occurred_at__date__lte=end)
    reviewable = all_events.exclude(status=Event.Status.ARCHIVED).count()
    confirmed_count = all_events.filter(status=Event.Status.CONFIRMED).count()
    coverage = (confirmed_count / reviewable) if reviewable else 0
    docs = Document.objects.filter(source__region_scope=region)
    quarantine = docs.filter(processing_status=Document.ProcessingStatus.QUARANTINE).count()
    without_date = docs.filter(published_at__isnull=True).count()
    sources = Source.objects.filter(region_scope=region, is_active=True).count()
    errors = Source.objects.filter(region_scope=region).exclude(last_error="").count()
    index = None
    if latest:
        components = latest.components_json or {}
        index = {
            "value": latest.index_value,
            "status": components.get("status", "недостаточно данных"),
            "delta": delta,
            "version": latest.method_version,
            "event_count": confirmed_count,
            "sources": len(source_ids),
            "coverage": round(coverage, 2),
            "warning": components.get("warning"),
            "components": components.get("events", []),
            "low_coverage": components.get("low_coverage", False),
        }
    return {
        "empty": latest is None,
        "metrics": metrics,
        "topics": topics,
        "events": list(confirmed.order_by("-occurred_at")[:8]),
        "index": index,
        "quality": {
            "quarantine": quarantine,
            "without_date": without_date,
            "sources": sources,
            "source_errors": errors,
            "coverage": round(coverage, 2),
            "kpi": "не измерено",
        },
    }


def timeline_points(metrics) -> list[dict]:
    points = []
    for item in metrics:
        components = item.components_json or {}
        points.append(
            {
                "date": item.date.isoformat(),
                "value": item.index_value,
                "low_coverage": bool(components.get("low_coverage")),
                "status": components.get("status"),
            }
        )
    return points
