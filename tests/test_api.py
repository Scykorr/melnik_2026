import json
import re

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.audit.models import AuditEntry
from apps.documents.services import ingest_payload
from apps.events.models import Event
from apps.events.services import transition_event
from apps.reports.services import build_report
from tests.test_domain import _text


@pytest.fixture
def api():
    return APIClient()


def _event(world, url, fact):
    document, _created = ingest_payload(
        source=world.source,
        url=url,
        title="Собрание жителей",
        text=_text("ремонта теплосетей", fact),
        published_at=timezone.now(),
        metadata={"fact_code": fact},
    )
    return document.links.get().event


def test_api_filters_pagination_and_roles(world, api):
    for index in range(3):
        _event(world, f"https://demo.example.com/api-{index}", f"api-{index}")
    api.force_authenticate(world.analyst)
    response = api.get("/api/v1/events/?region=NORTH&page_size=10000")
    assert response.status_code == 200
    assert response.data["count"] == 3
    assert len(response.data["results"]) <= 100
    assert "request_id" in response.data
    blob = json.dumps(response.data, ensure_ascii=False)
    assert "author" not in response.json()["results"][0]
    assert "паспорт" not in blob
    detail = api.get(f"/api/v1/events/{Event.objects.first().pk}/")
    assert "clean_text" in detail.data["documents"][0]
    assert "author" not in detail.data["documents"][0]
    operator = User.objects.create_user("op", password="Pass-word-123", role=User.Role.OPERATOR)
    api.force_authenticate(operator)
    denied = api.post(f"/api/v1/events/{Event.objects.first().pk}/confirm/", {"comment": "нельзя"}, format="json")
    assert denied.status_code == 403
    anonymous = APIClient()
    assert anonymous.get("/api/v1/events/").status_code in {401, 403}


def test_confirm_reject_and_audit_api(world, api):
    event = _event(world, "https://demo.example.com/confirm", "confirm")
    transition_event(event=event, new_status="in_review", actor=world.analyst, comment="проверка")
    api.force_authenticate(world.analyst)
    response = api.post(f"/api/v1/events/{event.pk}/confirm/", {"comment": "подтверждаю"}, format="json")
    assert response.status_code == 200
    assert response.data["status"] == "confirmed"
    auditor = User.objects.create_user("aud", password="Pass-word-123", role=User.Role.AUDITOR)
    api.force_authenticate(auditor)
    audit = api.get("/api/v1/audit/")
    assert audit.status_code == 200
    assert AuditEntry.objects.filter(action="event_status_changed").exists()
    api.force_authenticate(world.analyst)
    hidden = api.get("/api/v1/audit/")
    assert hidden.status_code == 403


def test_report_approve_api_is_frozen(world, api):
    event = _event(world, "https://demo.example.com/rep", "rep")
    transition_event(event=event, new_status="in_review", actor=world.analyst, comment="проверка")
    event.refresh_from_db()
    transition_event(event=event, new_status="confirmed", actor=world.analyst, comment="подтверждено")
    approver = User.objects.create_user("apr", password="Pass-word-123", role=User.Role.APPROVER)
    end = timezone.localdate()
    report = build_report(region=world.region, period_start=end, period_end=end, user=world.analyst, title="ИАМ «Регион»")
    api.force_authenticate(world.analyst)
    denied = api.post(f"/api/v1/reports/{report.pk}/approve/", {}, format="json")
    assert denied.status_code == 403
    api.force_authenticate(approver)
    approved = api.post(f"/api/v1/reports/{report.pk}/approve/", {}, format="json")
    assert approved.status_code == 200
    again = api.post(f"/api/v1/reports/{report.pk}/approve/", {}, format="json")
    assert again.status_code == 409


def test_health_and_ui_flow(world, client):
    event = _event(world, "https://demo.example.com/ui", "ui-flow")
    assert client.get("/").status_code == 302
    assert client.login(username="analyst-test", password="Pass-word-123")
    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert "синтетические".encode() in dashboard.content
    queue = client.get("/queue/")
    assert queue.status_code == 200
    card = client.get(f"/events/{event.pk}/")
    assert card.status_code == 200
    client.post(f"/events/{event.pk}/transition/", {"status": "in_review", "comment": "беру в работу"})
    client.post(f"/events/{event.pk}/transition/", {"status": "confirmed", "comment": "событие подтверждено"})
    event.refresh_from_db()
    assert event.status == "confirmed"
    created = client.post(
        "/reports/new/",
        {
            "title": "Проект ИАМ «Регион»",
            "region": world.region.pk,
            "period_start": timezone.localdate().isoformat(),
            "period_end": timezone.localdate().isoformat(),
        },
    )
    assert created.status_code == 302
    operator = User.objects.create_user("operator-ui", password="Pass-word-123", role=User.Role.OPERATOR)
    client.force_login(operator)
    denied = client.post(f"/events/{event.pk}/transition/", {"status": "rejected", "comment": "оператор не может"})
    assert denied.status_code == 403
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 200


def test_pages_load_assets_locally(client):
    for path in ("/accounts/login/", "/admin/login/"):
        html = client.get(path).content.decode()
        assert "cdn." not in html
        assert "googleapis" not in html
        assert "jsdelivr" not in html
        assert "unpkg" not in html
        for asset in re.findall(r'(?:src|href)="([^"]+)"', html):
            assert not asset.startswith(("http://", "https://", "//"))
