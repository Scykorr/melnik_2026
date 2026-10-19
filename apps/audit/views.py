from django.core.paginator import Paginator
from django.shortcuts import render
from django.views import View

from apps.audit.models import AuditEntry
from apps.common.mixins import RoleRequiredMixin


class AuditListView(RoleRequiredMixin, View):
    roles = ("auditor",)

    def get(self, request):
        qs = AuditEntry.objects.select_related("actor")
        if request.GET.get("action"):
            qs = qs.filter(action=request.GET["action"])
        page = Paginator(qs, 30).get_page(request.GET.get("page"))
        return render(request, "audit/list.html", {"page": page})
