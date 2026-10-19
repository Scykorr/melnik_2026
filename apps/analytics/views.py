from datetime import date

from django.views.generic import TemplateView

from apps.analytics.formula import FormulaParams
from apps.analytics.selectors import dashboard_payload, timeline_points
from apps.common.mixins import RoleRequiredMixin
from apps.common.scope import get_scope


def _scale(points, scale):
    if scale != "week":
        return points
    buckets = {}
    for point in points:
        key = date.fromisoformat(point["date"]).strftime("%G-W%V")
        bucket = buckets.setdefault(key, {"date": key, "values": [], "low_coverage": False, "status": "ok"})
        if point["value"] is not None:
            bucket["values"].append(point["value"])
        bucket["low_coverage"] = bucket["low_coverage"] or bool(point["low_coverage"])
    return [
        {
            "date": item["date"],
            "value": round(sum(item["values"]) / len(item["values"]), 2) if item["values"] else None,
            "low_coverage": item["low_coverage"],
            "status": item["status"],
        }
        for item in buckets.values()
    ]


class DashboardView(RoleRequiredMixin, TemplateView):
    roles = ("analyst", "approver", "operator", "auditor")
    template_name = "dashboard/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        scope = get_scope(self.request)
        payload = dashboard_payload(scope["region"], scope["start"], scope["end"])
        metrics = payload.get("metrics") or []
        context.update(payload)
        context["scope"] = scope
        context["timeline"] = _scale(timeline_points(metrics), self.request.GET.get("scale", "day"))
        context["formula"] = FormulaParams()
        context["scale"] = self.request.GET.get("scale", "day")
        return context
