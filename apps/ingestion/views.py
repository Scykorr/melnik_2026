import csv
import io
import json

from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils.dateparse import parse_datetime
from django.views import View

from apps.common.exceptions import SsrfError
from apps.common.mixins import RoleRequiredMixin
from apps.common.ssrf import validate_public_http_url
from apps.documents.services import ingest_payload
from apps.ingestion.adapters import fetch_public
from apps.ingestion.errors import TemporaryIngestError
from apps.ingestion.forms import ImportForm, ManualUrlForm


class ManualUrlView(RoleRequiredMixin, View):
    roles = ("operator", "analyst")

    def get(self, request):
        return render(request, "ingestion/manual.html", {"form": ManualUrlForm()})

    def post(self, request):
        form = ManualUrlForm(request.POST)
        if not form.is_valid():
            return render(request, "ingestion/manual.html", {"form": form})
        url = form.cleaned_data["url"]
        try:
            validate_public_http_url(url)
        except SsrfError as exc:
            form.add_error("url", str(exc))
            return render(request, "ingestion/manual.html", {"form": form})
        text = form.cleaned_data["text"]
        mime = "text/plain"
        if not text:
            try:
                _final, data, mime = fetch_public(url)
                text = data.decode("utf-8", errors="replace")
            except (SsrfError, TemporaryIngestError) as exc:
                form.add_error("url", str(exc))
                return render(request, "ingestion/manual.html", {"form": form})
        document, created = ingest_payload(
            source=form.cleaned_data["source"],
            url=url,
            title=form.cleaned_data["title"] or url,
            text=text,
            published_at=form.cleaned_data["published_at"],
            mime=mime,
            request=request,
        )
        if document.processing_status == "quarantine":
            messages.warning(request, f"Материал помещён в карантин: {document.quarantine_reason}")
        elif created:
            messages.success(request, "Публикация добавлена в очередь обработки")
        else:
            messages.info(request, "Такая публикация уже есть, повтор не создан")
        return redirect("queue")


class ImportView(RoleRequiredMixin, View):
    roles = ("operator",)

    def get(self, request):
        return render(request, "ingestion/import.html", {"form": ImportForm()})

    def post(self, request):
        form = ImportForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(request, "ingestion/import.html", {"form": form})
        upload = form.cleaned_data["upload"]
        if upload.size > 2_000_000:
            form.add_error("upload", "Файл больше 2 МБ")
            return render(request, "ingestion/import.html", {"form": form})
        raw = upload.read().decode("utf-8-sig")
        name = upload.name.lower()
        rows = []
        if name.endswith(".json"):
            payload = json.loads(raw)
            rows = payload.get("items", payload if isinstance(payload, list) else [])
        else:
            rows = list(csv.DictReader(io.StringIO(raw)))
        created = 0
        for row in rows:
            published = parse_datetime(str(row.get("published_at", "")).replace("Z", "+00:00"))
            _doc, was_created = ingest_payload(
                source=form.cleaned_data["source"],
                url=row.get("url", ""),
                title=row.get("title", ""),
                text=row.get("text", ""),
                published_at=published,
                language=row.get("language") or "ru",
                metadata=row.get("metadata") if isinstance(row.get("metadata"), dict) else {},
                mime="application/json" if name.endswith(".json") else "text/csv",
                request=request,
            )
            created += int(was_created)
        messages.success(request, f"Импорт завершён. Новых записей: {created}.")
        return redirect("sources")
