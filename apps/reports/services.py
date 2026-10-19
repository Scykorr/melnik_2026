from __future__ import annotations

import hashlib
import json
from collections import Counter

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.analytics.models import DailyMetric
from apps.audit.services import write_audit
from apps.common.exceptions import ImmutableReportError
from apps.events.models import Event
from apps.reports.exporters import render_docx, render_pdf
from apps.reports.models import Report

WRITERS = {"analyst", "admin"}
APPROVERS = {"approver", "admin"}


def completeness_issues(report: Report) -> list[str]:
    facts = (report.body_json or {}).get("facts") or []
    issues = []
    if not facts:
        issues.append("Нет подтверждённых событий со ссылками")
    if any(not fact.get("sources") for fact in facts):
        issues.append("Есть факт без ссылки на публикацию")
    if not (report.body_json or {}).get("limitations"):
        issues.append("Не заполнен раздел ограничений")
    return issues


def _body_for(region, period_start, period_end) -> tuple[dict, str]:
    events = list(
        Event.objects.filter(
            region=region,
            status=Event.Status.CONFIRMED,
            occurred_at__date__gte=period_start,
            occurred_at__date__lte=period_end,
        )
        .select_related("topic")
        .prefetch_related("links__document__source")
    )
    facts = []
    for event in events:
        sources = []
        for link in event.links.all():
            if link.document.deleted_at:
                continue
            sources.append(
                {
                    "name": link.document.source.name,
                    "url": link.document.canonical_url,
                    "primary": link.is_primary,
                }
            )
        facts.append(
            {
                "event_id": event.pk,
                "title": event.title,
                "topic": event.topic.name,
                "summary": (event.summary or "")[:500],
                "sources": sources,
            }
        )
    topic_counts = dict(Counter(event.topic.name for event in events))
    metrics = list(
        DailyMetric.objects.filter(
            region=region,
            date__gte=period_start,
            date__lte=period_end,
            method_version=settings.FORMULA_VERSION,
        ).order_by("date")
    )
    ready = [item for item in metrics if item.index_value is not None]
    auto = {
        "summary": (
            f"За период {period_start.isoformat()} — {period_end.isoformat()} "
            f"подтверждено событий: {len(facts)}. Текст собран автоматически и требует правки аналитика."
        ),
        "topics": ", ".join(f"{name}: {count}" for name, count in topic_counts.items()) or "Подтверждённых тем нет",
        "dynamics": f"Дней с рассчитанным индексом: {len(ready)} из {len(metrics)}.",
        "facts": "Ниже перечислены только подтверждённые события и их публикации.",
        "limitations": (
            "Индекс и подборка описывают открытый информационный поток, а не взгляды жителей. "
            "Охват источников может быть неполным. Снижение трудозатрат на выпуск ИАМ: не измерено."
        ),
    }
    body = {
        "project_title": settings.PROJECT_TITLE,
        "topics": topic_counts,
        "dynamics": [
            {"date": item.date.isoformat(), "index": item.index_value, "status": (item.components_json or {}).get("status")}
            for item in metrics
        ],
        "facts": facts,
        "limitations": auto["limitations"],
        "auto_text": auto,
        "approved_text": {"summary": "", "topics": "", "dynamics": "", "facts": "", "limitations": ""},
        "kpi": {"t0": "не измерено", "t1": "не измерено", "k_t": "не измерено"},
    }
    payload = json.dumps({"events": [event.pk for event in events], "method": settings.FORMULA_VERSION}, sort_keys=True)
    return body, hashlib.sha256(payload.encode()).hexdigest()


@transaction.atomic
def build_report(*, region, period_start, period_end, user, title: str) -> Report:
    if user.role not in WRITERS:
        raise PermissionDenied
    if period_end < period_start:
        raise ImmutableReportError("Конец периода раньше начала")
    body, digest = _body_for(region, period_start, period_end)
    version = Report.objects.filter(region=region, period_start=period_start, period_end=period_end).count() + 1
    report = Report.objects.create(
        region=region,
        period_start=period_start,
        period_end=period_end,
        title=title[:400],
        version=version,
        executive_summary=body["auto_text"]["summary"],
        body_json=body,
        input_hash=digest,
        method_version=settings.FORMULA_VERSION,
        created_by=user,
    )
    write_audit(
        actor=user,
        action="report_created",
        object_type="report",
        object_id=report.pk,
        after={"version": version, "input_hash": digest, "status": report.status},
    )
    return report


@transaction.atomic
def update_draft(*, report: Report, user, executive_summary: str, approved_text: dict) -> Report:
    if user.role not in WRITERS:
        raise PermissionDenied
    if report.status in {Report.Status.APPROVED, Report.Status.PUBLISHED}:
        raise ImmutableReportError("Утверждённую версию отчёта нельзя изменять")
    body = dict(report.body_json or {})
    body["approved_text"] = {
        "summary": approved_text.get("summary", ""),
        "topics": approved_text.get("topics", ""),
        "dynamics": approved_text.get("dynamics", ""),
        "facts": approved_text.get("facts", ""),
        "limitations": approved_text.get("limitations", ""),
    }
    report.body_json = body
    report.executive_summary = executive_summary
    report.save()
    write_audit(
        actor=user,
        action="report_draft_updated",
        object_type="report",
        object_id=report.pk,
        after={"status": report.status, "input_hash": report.input_hash},
    )
    return report


@transaction.atomic
def submit_report(*, report: Report, user) -> Report:
    if user.role not in WRITERS:
        raise PermissionDenied
    if report.status != Report.Status.DRAFT:
        raise ImmutableReportError("На согласование можно отправить только черновик")
    report.status = Report.Status.IN_REVIEW
    report.save()
    write_audit(
        actor=user,
        action="report_submitted",
        object_type="report",
        object_id=report.pk,
        after={"status": report.status},
    )
    return report


@transaction.atomic
def approve_report(*, report: Report, user, request=None) -> Report:
    if user.role not in APPROVERS:
        raise PermissionDenied
    locked = Report.objects.select_for_update().get(pk=report.pk)
    if locked.status in {Report.Status.APPROVED, Report.Status.PUBLISHED}:
        raise ImmutableReportError("Утверждённую версию отчёта нельзя изменять")
    if locked.status not in {Report.Status.DRAFT, Report.Status.IN_REVIEW}:
        raise ImmutableReportError("Отчёт нельзя утвердить из текущего состояния")
    issues = completeness_issues(locked)
    if issues:
        raise ImmutableReportError("; ".join(issues))
    content = render_pdf(locked)
    locked.file.save(f"iam-{locked.pk}-v{locked.version}.pdf", ContentFile(content), save=False)
    locked.status = Report.Status.APPROVED
    locked.approved_by = user
    locked.approved_at = timezone.now()
    locked.save()
    write_audit(
        actor=user,
        action="report_approved",
        object_type="report",
        object_id=locked.pk,
        after={"status": locked.status, "input_hash": locked.input_hash, "version": locked.version},
        request=request,
    )
    return locked


@transaction.atomic
def fork_version(*, report: Report, user) -> Report:
    if user.role not in WRITERS:
        raise PermissionDenied
    clone = Report(
        region=report.region,
        period_start=report.period_start,
        period_end=report.period_end,
        status=Report.Status.DRAFT,
        version=report.version + 1,
        title=report.title,
        executive_summary=report.executive_summary,
        body_json=report.body_json,
        input_hash=report.input_hash,
        template_version=report.template_version,
        method_version=report.method_version,
        created_by=user,
    )
    clone.save()
    write_audit(
        actor=user,
        action="report_version_forked",
        object_type="report",
        object_id=clone.pk,
        after={"from": report.pk, "version": clone.version},
    )
    return clone


def export_bytes(report: Report, fmt: str) -> tuple[bytes, str, str]:
    if fmt == "docx":
        return render_docx(report), "application/vnd.openxmlformats-officedocument.wordprocessingml.document", f"iam-{report.pk}.docx"
    return render_pdf(report), "application/pdf", f"iam-{report.pk}.pdf"
