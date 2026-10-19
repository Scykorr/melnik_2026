from __future__ import annotations

import csv
import io
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

import feedparser
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.common.exceptions import SsrfError
from apps.common.ssrf import validate_public_http_url, validate_redirect_target
from apps.ingestion.errors import TemporaryIngestError


@dataclass
class FetchedItem:
    url: str
    title: str
    text: str
    published_at: datetime | None
    language: str = "ru"
    metadata: dict | None = None
    mime: str = "text/html"


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_public(url: str, allowlist: list[str] | None = None, hops: int = 3) -> tuple[str, bytes, str]:
    current = validate_public_http_url(url, allowlist)
    for _ in range(hops + 1):
        request = Request(current, headers={"User-Agent": "IAM-Region/1.0"}, method="GET")
        opener = build_opener(_NoRedirect)
        try:
            with opener.open(request, timeout=8) as response:
                mime = (response.headers.get("Content-Type") or "application/octet-stream").split(";")[0].strip()
                data = response.read(settings.MAX_DOCUMENT_CHARS + 1)
                return current, data, mime
        except HTTPError as exc:
            if exc.code in {301, 302, 303, 307, 308}:
                current = validate_redirect_target(current, exc.headers.get("Location", ""), allowlist)
                continue
            if exc.code in {408, 429, 500, 502, 503, 504}:
                raise TemporaryIngestError("Временная ошибка источника") from exc
            raise SsrfError("Источник ответил отказом") from exc
        except URLError as exc:
            raise TemporaryIngestError("Источник временно недоступен") from exc
        except TimeoutError as exc:
            raise TemporaryIngestError("Истекло время ожидания источника") from exc
    raise SsrfError("Слишком много перенаправлений")


def _read_fixture(relative: str) -> bytes:
    root = (Path(settings.BASE_DIR) / "fixtures").resolve()
    target = (root / relative).resolve()
    if root not in target.parents and target != root:
        raise SsrfError("Путь выходит за каталог fixtures")
    if not target.is_file():
        raise SsrfError("Файл импорта не найден")
    return target.read_bytes()


def load_feed_bytes(source) -> tuple[bytes, str]:
    feed = (source.feed_url or "").strip()
    if feed.startswith("http://") or feed.startswith("https://"):
        _final, data, mime = fetch_public(feed)
        return data, mime
    if not feed:
        return b"", "text/plain"
    mime = "application/json" if feed.endswith(".json") else "text/csv"
    return _read_fixture(feed), mime


class BaseSourceAdapter(ABC):
    source_type = ""

    @abstractmethod
    def fetch(self, source) -> list[FetchedItem]:
        raise NotImplementedError


def _published(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = parse_datetime(str(value).replace("Z", "+00:00"))
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


class RssAdapter(BaseSourceAdapter):
    source_type = "rss"

    def fetch(self, source) -> list[FetchedItem]:
        data, _mime = load_feed_bytes(source)
        if not data:
            return []
        parsed = feedparser.parse(data)
        items = []
        for entry in parsed.entries:
            published = None
            if getattr(entry, "published_parsed", None):
                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.get_current_timezone())
            items.append(
                FetchedItem(
                    url=getattr(entry, "link", "") or "",
                    title=getattr(entry, "title", "") or "",
                    text=getattr(entry, "summary", "") or getattr(entry, "description", "") or "",
                    published_at=published,
                    mime="application/rss+xml",
                )
            )
        return items


class AtomAdapter(RssAdapter):
    source_type = "atom"


class JsonAdapter(BaseSourceAdapter):
    source_type = "json"

    def fetch(self, source) -> list[FetchedItem]:
        data, _mime = load_feed_bytes(source)
        if not data:
            return []
        payload = json.loads(data.decode("utf-8"))
        rows = payload.get("items", payload if isinstance(payload, list) else [])
        return [
            FetchedItem(
                url=row.get("url", ""),
                title=row.get("title", ""),
                text=row.get("text", ""),
                published_at=_published(row.get("published_at")),
                language=row.get("language", "ru"),
                metadata=row.get("metadata") or {},
                mime="application/json",
            )
            for row in rows
        ]


class CsvAdapter(BaseSourceAdapter):
    source_type = "csv"

    def fetch(self, source) -> list[FetchedItem]:
        data, _mime = load_feed_bytes(source)
        if not data:
            return []
        reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
        return [
            FetchedItem(
                url=row.get("url", ""),
                title=row.get("title", ""),
                text=row.get("text", ""),
                published_at=_published(row.get("published_at")),
                language=row.get("language") or "ru",
                mime="text/csv",
            )
            for row in reader
        ]


class ManualAdapter(BaseSourceAdapter):
    source_type = "manual"

    def fetch(self, source) -> list[FetchedItem]:
        return []


class OfficialApiAdapter(BaseSourceAdapter):
    """Интерфейс будущего официального API. Без ключа сеть не вызывается."""

    source_type = "official_api"

    def fetch(self, source) -> list[FetchedItem]:
        return []


ADAPTERS: dict[str, BaseSourceAdapter] = {
    "rss": RssAdapter(),
    "atom": AtomAdapter(),
    "json": JsonAdapter(),
    "csv": CsvAdapter(),
    "manual": ManualAdapter(),
    "official_api": OfficialApiAdapter(),
}
