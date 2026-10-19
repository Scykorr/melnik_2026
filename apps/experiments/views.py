import csv

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views import View

from apps.common.mixins import RoleRequiredMixin
from apps.experiments.calculations import labor_summary, store_summary
from apps.experiments.forms import EconomyForm, WorkSessionForm
from apps.experiments.models import EvaluationRun, StudyPackage, WorkSession


class ExperimentHomeView(RoleRequiredMixin, View):
    roles = ("analyst", "approver", "auditor")

    def get(self, request):
        summary = labor_summary()
        runs = EvaluationRun.objects.all()[:20]
        external = [item for item in runs if item.dataset_kind == "external" and not item.unreliable]
        return render(
            request,
            "experiments/index.html",
            {
                "summary": summary,
                "packages": StudyPackage.objects.all(),
                "sessions": WorkSession.objects.select_related("package")[:50],
                "runs": runs,
                "show_factual_metrics": bool(external),
                "external_runs": external,
            },
        )

    def post(self, request):
        package_id = request.POST.get("package")
        package = StudyPackage.objects.filter(pk=package_id).first()
        if package:
            store_summary(package)
            messages.success(request, "Снимок сопоставления сохранён")
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        if request.POST.get("export") == "csv":
            response["Content-Disposition"] = 'attachment; filename="work_sessions.csv"'
            writer = csv.writer(response)
            writer.writerow(
                ["package", "analyst_code", "mode", "status", "active_minutes", "wait_minutes", "errors", "comparable"]
            )
            for session in WorkSession.objects.select_related("package"):
                writer.writerow(
                    [
                        session.package.code,
                        session.analyst_code,
                        session.mode,
                        session.status,
                        session.human_active_minutes,
                        session.wait_background_minutes,
                        session.error_count,
                        session.comparable,
                    ]
                )
            return response
        return redirect("experiments")


class SessionCreateView(RoleRequiredMixin, View):
    roles = ("analyst", "approver")

    def get(self, request):
        return render(request, "experiments/session_form.html", {"form": WorkSessionForm()})

    def post(self, request):
        form = WorkSessionForm(request.POST)
        if not form.is_valid():
            return render(request, "experiments/session_form.html", {"form": form})
        session = form.save(commit=False)
        session.app_version = settings.APP_VERSION
        session.save()
        messages.success(request, "Сессия записана. Черновик не считается выпуском ИАМ.")
        return redirect("experiments")


class EconomyView(RoleRequiredMixin, View):
    roles = ("analyst", "approver", "auditor")

    def get(self, request):
        return render(request, "experiments/economy.html", {"form": EconomyForm(), "result": None})

    def post(self, request):
        form = EconomyForm(request.POST)
        result = form.result() if form.is_valid() else None
        return render(request, "experiments/economy.html", {"form": form, "result": result})
