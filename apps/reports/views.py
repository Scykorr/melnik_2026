from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from apps.common.exceptions import ImmutableReportError
from apps.common.mixins import RoleRequiredMixin
from apps.reports.forms import ReportCreateForm, ReportDraftForm
from apps.reports.models import Report
from apps.reports.services import (
    approve_report,
    build_report,
    completeness_issues,
    export_bytes,
    submit_report,
    update_draft,
)


class ReportListView(RoleRequiredMixin, View):
    roles = ("analyst", "approver", "auditor")

    def get(self, request):
        return render(request, "reports/list.html", {"reports": Report.objects.select_related("region", "created_by")})


class ReportCreateView(RoleRequiredMixin, View):
    roles = ("analyst",)

    def get(self, request):
        return render(request, "reports/create.html", {"form": ReportCreateForm()})

    def post(self, request):
        form = ReportCreateForm(request.POST)
        if not form.is_valid():
            return render(request, "reports/create.html", {"form": form})
        report = build_report(
            region=form.cleaned_data["region"],
            period_start=form.cleaned_data["period_start"],
            period_end=form.cleaned_data["period_end"],
            user=request.user,
            title=form.cleaned_data["title"],
        )
        messages.success(request, "Черновик ИАМ создан. Автотекст отделён от текста аналитика.")
        return redirect("report-detail", pk=report.pk)


class ReportBuilderView(RoleRequiredMixin, View):
    roles = ("analyst", "approver", "auditor")

    def get(self, request, pk):
        report = get_object_or_404(Report.objects.select_related("region"), pk=pk)
        approved = (report.body_json or {}).get("approved_text") or {}
        form = ReportDraftForm(
            initial={
                "executive_summary": report.executive_summary,
                "summary": approved.get("summary", ""),
                "topics": approved.get("topics", ""),
                "dynamics": approved.get("dynamics", ""),
                "facts": approved.get("facts", ""),
                "limitations": approved.get("limitations", ""),
            }
        )
        return render(
            request,
            "reports/builder.html",
            {"report": report, "form": form, "issues": completeness_issues(report), "frozen": report.status in {Report.Status.APPROVED, Report.Status.PUBLISHED}},
        )

    def post(self, request, pk):
        report = get_object_or_404(Report, pk=pk)
        form = ReportDraftForm(request.POST)
        if form.is_valid() and request.user.role in {"analyst", "admin"}:
            try:
                update_draft(
                    report=report,
                    user=request.user,
                    executive_summary=form.cleaned_data["executive_summary"],
                    approved_text=form.cleaned_data,
                )
            except ImmutableReportError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, "Черновик сохранён")
        return redirect("report-detail", pk=pk)


class ReportApproveView(RoleRequiredMixin, View):
    roles = ("approver",)

    def post(self, request, pk):
        report = get_object_or_404(Report, pk=pk)
        action = request.POST.get("action", "approve")
        try:
            if action == "submit" and request.user.role == "admin":
                submit_report(report=report, user=request.user)
            elif action == "submit":
                messages.error(request, "Отправку черновика выполняет аналитик")
                return redirect("report-detail", pk=pk)
            else:
                approve_report(report=report, user=request.user, request=request)
        except ImmutableReportError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Версия зафиксирована и больше не редактируется")
        return redirect("report-detail", pk=pk)


class ReportSubmitView(RoleRequiredMixin, View):
    roles = ("analyst",)

    def post(self, request, pk):
        report = get_object_or_404(Report, pk=pk)
        try:
            submit_report(report=report, user=request.user)
        except ImmutableReportError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Черновик передан на согласование")
        return redirect("report-detail", pk=pk)


class ReportExportView(RoleRequiredMixin, View):
    roles = ("analyst", "approver", "auditor")

    def get(self, request, pk, fmt):
        report = get_object_or_404(Report.objects.select_related("region"), pk=pk)
        if fmt not in {"pdf", "docx"}:
            return HttpResponse("Формат не поддерживается", status=400)
        if report.status in {Report.Status.APPROVED, Report.Status.PUBLISHED} and fmt == "pdf" and report.file:
            content = report.file.read()
            report.file.seek(0)
            mime = "application/pdf"
            filename = report.file.name.rsplit("/", 1)[-1]
        else:
            content, mime, filename = export_bytes(report, fmt)
        response = HttpResponse(content, content_type=mime)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
