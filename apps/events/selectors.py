from __future__ import annotations

from datetime import timedelta

from django.db.models import Q

from apps.events.models import Event


def filtered_events(params: dict):
    qs = Event.objects.select_related("region", "topic", "assigned_to")
    if params.get("region"):
        qs = qs.filter(region__code=params["region"])
    if params.get("status"):
        qs = qs.filter(status=params["status"])
    if params.get("topic"):
        qs = qs.filter(topic__code=params["topic"])
    if params.get("source"):
        qs = qs.filter(links__document__source_id=params["source"]).distinct()
    if params.get("confidence_min"):
        qs = qs.filter(confidence__gte=params["confidence_min"])
    if params.get("date_from"):
        qs = qs.filter(occurred_at__date__gte=params["date_from"])
    if params.get("date_to"):
        qs = qs.filter(occurred_at__date__lte=params["date_to"])
    query = (params.get("q") or "").strip()
    if query:
        qs = qs.filter(Q(title__icontains=query) | Q(summary__icontains=query))
    ordering = params.get("ordering") or "-occurred_at"
    allowed = {"occurred_at", "-occurred_at", "confidence", "-confidence", "status", "-status", "title", "-title"}
    if ordering not in allowed:
        ordering = "-occurred_at"
    return qs.order_by(ordering)


def similar_events(event: Event):
    window = timedelta(days=14)
    return (
        Event.objects.filter(
            region=event.region,
            topic=event.topic,
            occurred_at__range=(event.occurred_at - window, event.occurred_at + window),
        )
        .exclude(pk=event.pk)
        .order_by("-occurred_at")[:8]
    )
