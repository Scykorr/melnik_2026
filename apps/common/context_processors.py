from __future__ import annotations

from apps.common.scope import get_scope
from apps.regions.models import Region


def shell(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {"project_short": "ИАМ «Регион»"}
    scope = get_scope(request)
    return {
        "project_short": "ИАМ «Регион»",
        "nav_regions": Region.objects.filter(is_active=True).order_by("name"),
        "scope": scope,
        "saved_filters": request.session.get("saved_filters", []),
    }
