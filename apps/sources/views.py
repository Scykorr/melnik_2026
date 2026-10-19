from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from apps.audit.services import write_audit
from apps.common.mixins import RoleRequiredMixin
from apps.ingestion.tasks import poll_source
from apps.sources.forms import SourceForm
from apps.sources.models import Source
from apps.sources.selectors import source_health


class SourceListView(RoleRequiredMixin, View):
    roles = ("operator", "analyst", "auditor")

    def get(self, request):
        return render(request, "sources/list.html", {"rows": source_health()})


class SourceCreateView(RoleRequiredMixin, View):
    roles = ("operator",)

    def get(self, request):
        return render(request, "sources/form.html", {"form": SourceForm()})

    def post(self, request):
        form = SourceForm(request.POST)
        if not form.is_valid():
            return render(request, "sources/form.html", {"form": form})
        source = form.save()
        write_audit(
            actor=request.user,
            action="source_saved",
            object_type="source",
            object_id=source.pk,
            after={"name": source.name, "weight": source.reliability_weight, "active": source.is_active},
            request=request,
        )
        messages.success(request, "Источник сохранён")
        return redirect("sources")


class SourcePollView(RoleRequiredMixin, View):
    roles = ("operator",)

    def post(self, request, pk):
        source = get_object_or_404(Source, pk=pk)
        poll_source.delay(source.pk)
        messages.success(request, "Повторный запуск поставлен в очередь. Секреты и трассировки не показываются.")
        return redirect("sources")
