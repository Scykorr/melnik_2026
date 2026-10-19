from datetime import timedelta

import pytest
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.accounts.models import User
from apps.analytics.formula import ContributionInput, FormulaParams, contribution, rolling_index
from apps.analytics.services import rebuild_region_metrics
from apps.audit.models import AuditEntry
from apps.common.exceptions import ImmutableReportError, SsrfError, TransitionError
from apps.common.ssrf import validate_public_http_url, validate_redirect_target
from apps.documents.classification import TOPIC_VERSION, classify_relevance, classify_topics
from apps.documents.dedup import should_merge_texts
from apps.documents.models import Document
from apps.documents.services import delete_document, ingest_payload
from apps.events.models import Event
from apps.events.services import assign_events, record_assessment, transition_event
from apps.reports.services import approve_report, build_report, fork_version, update_draft


def _text(subject, fact):
    return (
        f"Жители провели собрание и выдвинули коллективное требование по поводу {subject}. "
        f"Сюжет {fact}. Демонстрационная публикация."
    )


def test_relevance_separates_protest_and_comment():
    label, _confidence, _basis = classify_relevance(
        "Жители провели собрание и выдвинули коллективное требование отремонтировать теплосети."
    )
    assert label == "relevant"
    label, _confidence, basis = classify_relevance(
        "Комментарий читателя: один житель жалуется на бытовую жалобу крана."
    )
    assert label == "irrelevant"
    assert "жалоб" in basis or "комментар" in basis.lower() or basis


def test_topic_rules_version_and_class():
    code, _codes, basis = classify_topics("Коллективное требование о задержке зарплаты")
    assert code == "labor"
    assert TOPIC_VERSION in basis


def test_same_topic_does_not_merge_different_facts():
    left = _text("ремонта теплосетей на улице Примерной", "heat-01")
    right = _text("замены стояков жкх в доме 4", "pipes-19")
    merged, _score, explanation = should_merge_texts(left, right, left_fact="heat-01", right_fact="pipes-19")
    assert merged is False
    assert "не объединя" in explanation


def test_reprint_is_not_a_new_event(world):
    published = timezone.now() - timedelta(days=2)
    first, created = ingest_payload(
        source=world.source,
        url="https://demo.example.com/a",
        title="Собрание жителей: теплосети",
        text=_text("ремонта теплосетей", "heat-a"),
        published_at=published,
        metadata={"fact_code": "heat-a"},
    )
    second, created_second = ingest_payload(
        source=world.other,
        url="https://demo.example.com/b",
        title="Перепечатка: теплосети",
        text=_text("ремонта теплосетей", "heat-a") + " Перепечатка открытого сообщения.",
        published_at=published + timedelta(hours=1),
        metadata={"fact_code": "heat-a"},
    )
    other, _created = ingest_payload(
        source=world.source,
        url="https://demo.example.com/c",
        title="Собрание жителей: стояки",
        text=_text("замены стояков жкх в доме 4", "pipes-b"),
        published_at=published + timedelta(days=3),
        metadata={"fact_code": "pipes-b"},
    )
    assert created and created_second
    assert first.relevance_label == "relevant"
    assert Event.objects.count() == 2
    assert other.links.first().event_id != second.links.first().event_id
    assert first.links.first().event_id == second.links.first().event_id


def test_exact_dedup_is_idempotent(world):
    published = timezone.now()
    payload = dict(
        source=world.source,
        url="https://demo.example.com/same",
        title="Собрание",
        text=_text("ремонта теплосетей", "same"),
        published_at=published,
        metadata={"fact_code": "same"},
    )
    _doc, created = ingest_payload(**payload)
    _again, created_again = ingest_payload(**payload)
    assert created is True
    assert created_again is False
    assert Document.objects.filter(canonical_url="https://demo.example.com/same").count() == 1


def test_quarantine_does_not_confirm_event(world):
    document, created = ingest_payload(
        source=world.source,
        url="notaurl",
        title="Битый",
        text=_text("ремонта теплосетей", "bad"),
        published_at=timezone.now(),
    )
    assert created
    assert document.processing_status == Document.ProcessingStatus.QUARANTINE
    assert Event.objects.count() == 0


def test_html_is_cleaned(world):
    document, _created = ingest_payload(
        source=world.source,
        url="https://demo.example.com/html",
        title="Собрание жителей",
        text="<script>alert(1)</script><p>Жители провели собрание и выдвинули коллективное требование по поводу теплосетей.</p>",
        published_at=timezone.now(),
        metadata={"author": "скрыто", "fact_code": "html"},
    )
    assert "script" not in document.clean_text.lower()
    assert "alert" not in document.clean_text.lower()
    assert "author" not in document.metadata_json


def test_event_transitions(world):
    document, _created = ingest_payload(
        source=world.source,
        url="https://demo.example.com/flow",
        title="Собрание жителей",
        text=_text("ремонта теплосетей", "flow"),
        published_at=timezone.now() - timedelta(days=1),
        metadata={"fact_code": "flow"},
    )
    event = document.links.first().event
    with pytest.raises(TransitionError):
        transition_event(event=event, new_status=Event.Status.CONFIRMED, actor=world.analyst, comment="рано")
    transition_event(event=event, new_status=Event.Status.IN_REVIEW, actor=world.analyst, comment="беру")
    event.refresh_from_db()
    with pytest.raises(TransitionError):
        transition_event(event=event, new_status=Event.Status.CONFIRMED, actor=world.analyst, comment="")
    transition_event(event=event, new_status=Event.Status.CONFIRMED, actor=world.analyst, comment="подтверждаю событие")
    event.refresh_from_db()
    assert event.status == Event.Status.CONFIRMED
    assert event.reviewed_by == world.analyst
    with pytest.raises(TransitionError):
        transition_event(event=event, new_status=Event.Status.REJECTED, actor=world.analyst, comment="поздно менять")


def test_assessment_does_not_overwrite_analyst(world):
    document, _ = ingest_payload(
        source=world.source,
        url="https://demo.example.com/assess",
        title="Собрание жителей",
        text=_text("ремонта теплосетей", "assess"),
        published_at=timezone.now(),
        metadata={"fact_code": "assess"},
    )
    event = document.links.first().event
    transition_event(event=event, new_status=Event.Status.IN_REVIEW, actor=world.analyst, comment="проверка")
    event.refresh_from_db()
    transition_event(event=event, new_status=Event.Status.CONFIRMED, actor=world.analyst, comment="решение аналитика")
    event.refresh_from_db()
    before = event.relevance_score
    record_assessment(event=event, label="relevant", score=0.1, confidence=0.1, explanation={"basis": "повтор"})
    event.refresh_from_db()
    assert event.relevance_score == before
    assert event.status == Event.Status.CONFIRMED


def test_index_edges_and_confirmed_only(world):
    assert contribution(ContributionInput(1, 0, 1, 1, 1, 0)) == 0
    params = FormulaParams(history_window_days=4)
    assert rolling_index(1, [1, 1, 1], params)[1] == "недостаточно данных"
    assert rolling_index(5, [1, 1, 1, 1], params)[1] == "недостаточно данных"
    value, status = rolling_index(10, [1, 2, 3, 4], params)
    assert status == "ok" and value is not None
    short = FormulaParams(history_window_days=2)
    changed, _status = rolling_index(10, [1, 2, 8, 9], short)
    base, _status = rolling_index(10, [1, 2, 8, 9], FormulaParams(history_window_days=4))
    assert changed != base
    published = timezone.now() - timedelta(days=3)
    confirmed, _ = ingest_payload(
        source=world.source,
        url="https://demo.example.com/ipa",
        title="Собрание жителей",
        text=_text("ремонта теплосетей", "ipa"),
        published_at=published,
        metadata={"fact_code": "ipa"},
    )
    rejected, _ = ingest_payload(
        source=world.source,
        url="https://demo.example.com/ipa-no",
        title="Собрание жителей",
        text=_text("замены стояков жкх в доме 9", "ipa-no"),
        published_at=published - timedelta(days=5),
        metadata={"fact_code": "ipa-no"},
    )
    for document, status in ((confirmed, Event.Status.CONFIRMED), (rejected, Event.Status.REJECTED)):
        event = document.links.first().event
        transition_event(event=event, new_status=Event.Status.IN_REVIEW, actor=world.analyst, comment="проверка")
        event.refresh_from_db()
        transition_event(event=event, new_status=status, actor=world.analyst, comment="решение записано")
    end = timezone.localdate()
    rebuild_region_metrics(world.region.id, end - timedelta(days=40), end, FormulaParams(history_window_days=4))
    from apps.analytics.models import DailyMetric

    latest = DailyMetric.objects.filter(region=world.region, date=end).first()
    titles = " ".join(item["title"] for item in latest.components_json["events"])
    assert "стояков" not in titles
    rebuild_region_metrics(world.region.id, end - timedelta(days=40), end, FormulaParams(history_window_days=4))
    assert DailyMetric.objects.filter(region=world.region, date=end).count() == 1


def test_mass_reprint_lowers_novelty():
    single = contribution(ContributionInput(1, 1, 1, 1, 1, 0))
    reprinted = contribution(ContributionInput(1, 1, 1, 1, 0.1, 0))
    assert reprinted < single


def test_delete_recomputes_without_text_in_audit(world):
    document, _ = ingest_payload(
        source=world.source,
        url="https://demo.example.com/del",
        title="Собрание жителей",
        text=_text("ремонта теплосетей", "del"),
        published_at=timezone.now(),
        metadata={"fact_code": "del"},
    )
    delete_document(document=document, actor=world.analyst, reason="ошибочная загрузка")
    document.refresh_from_db()
    assert document.clean_text == ""
    entry = AuditEntry.objects.get(action="document_deleted")
    assert "теплосет" not in str(entry.before_json) + str(entry.after_json)


def test_ssrf_blocks_private_redirect_and_allowlist(monkeypatch):
    with pytest.raises(SsrfError):
        validate_public_http_url("http://127.0.0.1/admin")
    with pytest.raises(SsrfError):
        validate_public_http_url("http://169.254.169.254/latest")
    with pytest.raises(SsrfError):
        validate_public_http_url("file:///etc/passwd")
    monkeypatch.setattr(
        "apps.common.ssrf.socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("10.1.1.1", 443))],
    )
    with pytest.raises(SsrfError):
        validate_public_http_url("https://demo.example.com/feed")
    monkeypatch.setattr(
        "apps.common.ssrf.socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("1.1.1.1", 443))],
    )
    with pytest.raises(SsrfError):
        validate_redirect_target("https://demo.example.com/a", "http://127.0.0.1/hidden")
    with pytest.raises(SsrfError):
        validate_public_http_url("https://demo.example.com/a", allowlist=["allowed.example"])


def test_report_is_immutable_and_audit(world):
    document, _ = ingest_payload(
        source=world.source,
        url="https://demo.example.com/report",
        title="Собрание жителей",
        text=_text("ремонта теплосетей", "report"),
        published_at=timezone.now() - timedelta(days=1),
        metadata={"fact_code": "report"},
    )
    event = document.links.first().event
    transition_event(event=event, new_status=Event.Status.IN_REVIEW, actor=world.analyst, comment="проверка")
    event.refresh_from_db()
    transition_event(event=event, new_status=Event.Status.CONFIRMED, actor=world.analyst, comment="подтверждено")
    approver = User.objects.create_user("approver-test", password="Pass-word-123", role=User.Role.APPROVER)
    end = timezone.localdate()
    report = build_report(
        region=world.region,
        period_start=end - timedelta(days=10),
        period_end=end,
        user=world.analyst,
        title="Проект ИАМ «Регион»",
    )
    update_draft(report=report, user=world.analyst, executive_summary="Резюме аналитика", approved_text={"summary": "текст"})
    approve_report(report=report, user=approver)
    report.refresh_from_db()
    assert report.status == "approved"
    assert report.file
    clone = fork_version(report=report, user=world.analyst)
    assert clone.status == "draft"
    assert clone.pk != report.pk
    report.refresh_from_db()
    assert report.status == "approved"
    with pytest.raises(ImmutableReportError):
        update_draft(report=report, user=world.analyst, executive_summary="тайная правка", approved_text={})
    assert AuditEntry.objects.filter(action="report_approved", object_id=str(report.pk)).exists()
    payload = report.file.read()
    assert "Разработка автоматизированной системы мониторинга протестной активности".encode() in payload or b"IAM" in payload or payload[:4] == b"%PDF"


def test_permissions_and_missing_gold(world):
    operator = User.objects.create_user("operator-test", password="Pass-word-123", role=User.Role.OPERATOR)
    with pytest.raises(Exception):
        transition_event(
            event=Event.objects.create(
                region=world.region,
                occurred_at=timezone.now(),
                topic=world.housing,
                title="черновик",
                status=Event.Status.IN_REVIEW,
            ),
            new_status=Event.Status.CONFIRMED,
            actor=operator,
            comment="нельзя",
        )
    with pytest.raises(CommandError):
        call_command("evaluate_dedup", dataset="missing", method="tfidf", split="test")


def test_labor_and_effect_are_not_invented(db):
    from decimal import Decimal

    from apps.experiments.calculations import economic_effect, labor_summary

    assert labor_summary()["status"] == "не измерено"
    forecast = economic_effect(t0=Decimal("10"), t1=Decimal("12"), releases=Decimal("5"), hourly=Decimal("100"), operating=Decimal("1"), capex=Decimal("1000"))
    assert forecast["payback"] == "не достигается"
    assert forecast["label"].startswith("прогноз")


def test_seed_demo(db):
    call_command("seed_demo")
    assert Event.objects.count() == 20
    assert Document.objects.count() >= 60
    from apps.accounts.models import User
    from apps.regions.models import Region

    assert User.objects.filter(role=User.Role.AUDITOR).exists()
    assert Region.objects.count() == 3
    call_command("seed_demo")
    assert Event.objects.count() == 20


def test_assign_and_gold_evaluation(world):
    from pathlib import Path

    document, _created = ingest_payload(
        source=world.source,
        url="https://demo.example.com/assign",
        title="Собрание жителей",
        text=_text("ремонта теплосетей", "assign"),
        published_at=timezone.now(),
        metadata={"fact_code": "assign"},
    )
    event = document.links.get().event
    colleague = User.objects.create_user("colleague", password="Pass-word-123", role=User.Role.ANALYST)
    assigned = assign_events(event_ids=[event.pk], assignee=colleague, actor=world.analyst)
    event.refresh_from_db()
    assert assigned == 1
    assert event.status == Event.Status.IN_REVIEW
    assert event.assigned_to == colleague
    with pytest.raises(PermissionDenied):
        transition_event(event=event, new_status=Event.Status.CONFIRMED, actor=world.analyst, comment="чужая карточка")
    fixture = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "gold_sample.csv"
    call_command("import_gold", str(fixture), dataset="gold-tech", kind="synthetic")
    call_command("evaluate_dedup", dataset="gold-tech", method="tfidf", split="test")
    from apps.experiments.models import EvaluationRun

    run = EvaluationRun.objects.get(dataset="gold-tech")
    assert run.unreliable is True
    assert run.f1 is not None
    with pytest.raises(CommandError):
        call_command("evaluate_dedup", dataset="gold-tech", method="embedding", split="test")
