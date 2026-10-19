from __future__ import annotations

from datetime import date, timedelta

from django.utils import timezone

from apps.regions.models import Region


def get_scope(request):
    today = timezone.localdate()
    default_start = today - timedelta(days=89)
    region_code = request.GET.get("region") or request.session.get("scope_region") or ""
    start_raw = request.GET.get("date_from") or request.session.get("scope_start") or default_start.isoformat()
    end_raw = request.GET.get("date_to") or request.session.get("scope_end") or today.isoformat()
    query = (request.GET.get("q") or "").strip()
    if request.GET.get("region") is not None or request.GET.get("date_from"):
        request.session["scope_region"] = region_code
        request.session["scope_start"] = start_raw
        request.session["scope_end"] = end_raw
    try:
        start = date.fromisoformat(start_raw)
        end = date.fromisoformat(end_raw)
    except ValueError:
        start, end = default_start, today
    if end < start:
        start, end = default_start, today
    region = Region.objects.filter(code=region_code, is_active=True).first()
    if region is None:
        region = Region.objects.filter(is_active=True).order_by("name").first()
    return {"region": region, "start": start, "end": end, "q": query}
