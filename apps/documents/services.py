from __future__ import annotations

import hashlib
import re
from datetime import datetime
from urllib.parse import urlparse

import bleach
from bs4 import BeautifulSoup
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.audit.services import write_audit
from apps.documents.classification import (
    RELEVANCE_VERSION,
    TOPIC_VERSION,
    classify_relevance,
    classify_topics,
)
from apps.documents.models import Document
from apps.regions.models import Topic

BANNED_META = {
    "author",
    "authors",
    "user",
    "username",
    "person",
    "persons",
    "face",
    "faces",
    "email",
    "phone",
    "passport",
    "profile",
    "organizer",
    "participant",
}
ALLOWED_MIME = (
    "text/",
    "application/json",
    "application/xml",
    "application/rss",
    "application/atom",
    "application/xhtml",
)


def clean_html(value: str) -> str:
    soup = BeautifulSoup(value or "", "html.parser")
    for tag in soup(["script", "style", "iframe", "object"]):
        tag.decompose()
    text = soup.get_text("\n")
    text = bleach.clean(text, tags=[], attributes={}, strip=True)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\sа-яё-]", "", (title or "").lower(), flags=re.IGNORECASE)).strip()


def checksum_for(text: str) -> str:
    return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()


def scrub_metadata(data: dict | None) -> dict:
    if not isinstance(data, dict):
        return {}
    return {key: value for key, value in data.items() if str(key).lower() not in BANNED_META}


def quarantine_reason(*, url: str, published_at, mime: str, text: str) -> str:
    parsed = urlparse(url or "")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return "недопустимый URL"
    if published_at is None:
        return "нет даты публикации"
    if mime and not any(mime.lower().startswith(prefix) for prefix in ALLOWED_MIME):
        return "недопустимый тип содержимого"
    if text and len(text) > settings.MAX_DOCUMENT_CHARS:
        return "превышен допустимый размер"
    return ""


def _apply_classification(document: Document) -> None:
    label, confidence, basis = classify_relevance(document.clean_text or document.title)
    topic_code, topic_codes, topic_basis = classify_topics(f"{document.title}\n{document.clean_text}")
    document.relevance_label = label
    document.relevance_confidence = confidence
    document.rule_or_model_version = f"{RELEVANCE_VERSION}|{TOPIC_VERSION}"
    document.classification_basis = f"{basis}. {topic_basis}"
    document.topic_codes = topic_codes
    document.primary_topic = Topic.objects.filter(code=topic_code, is_active=True).first()
    if document.processing_status != Document.ProcessingStatus.QUARANTINE:
        document.processing_status = Document.ProcessingStatus.PROCESSED


@transaction.atomic
def ingest_payload(
    *,
    source,
    url: str,
    title: str,
    text: str,
    published_at: datetime | None,
    language: str = "ru",
    metadata: dict | None = None,
    mime: str = "text/plain",
    request=None,
) -> tuple[Document, bool]:
    """Идемпотентная загрузка. Точный дубль по источнику и checksum не создаёт вторую запись."""
    clean = clean_html(text)
    title_clean = clean_html(title)[:400] or "Без заголовка"
    reason = quarantine_reason(url=url, published_at=published_at, mime=mime, text=clean)
    checksum = checksum_for(clean or title_clean)
    existing = Document.objects.filter(source=source, canonical_url=url).first()
    if existing:
        return existing, False
    exact = (
        Document.objects.filter(source=source, checksum=checksum)
        .exclude(processing_status=Document.ProcessingStatus.DELETED)
        .first()
    )
    if exact and not reason:
        return exact, False
    status = Document.ProcessingStatus.QUARANTINE if reason else Document.ProcessingStatus.PENDING
    document = Document.objects.create(
        source=source,
        canonical_url=url[:1000],
        title=title_clean,
        published_at=published_at,
        fetched_at=timezone.now(),
        language=(language or "ru")[:12],
        raw_text="" if reason else clean,
        clean_text="" if reason else clean,
        checksum=checksum,
        metadata_json=scrub_metadata(metadata),
        processing_status=status,
        normalized_title=normalize_title(title_clean),
        quarantine_reason=reason,
    )
    if reason:
        document.relevance_label = Document.RelevanceLabel.UNCLASSIFIED
        document.classification_basis = "Документ в карантине и не образует событие"
        document.save()
        return document, True
    _apply_classification(document)
    document.save()
    if document.relevance_label == Document.RelevanceLabel.RELEVANT and document.primary_topic_id:
        from apps.events.services import propose_event_for_document

        propose_event_for_document(document)
    write_audit(
        actor=getattr(request, "user", None),
        action="document_ingested",
        object_type="document",
        object_id=document.pk,
        after={"status": document.processing_status, "relevance": document.relevance_label},
        request=request,
    )
    return document, True


@transaction.atomic
def delete_document(*, document: Document, actor, reason: str, request=None) -> Document:
    if not (reason or "").strip():
        raise ValueError("Нужно основание удаления")
    region_ids = list(document.links.values_list("event__region_id", flat=True).distinct())
    before = {"status": document.processing_status, "checksum": document.checksum}
    document.processing_status = Document.ProcessingStatus.DELETED
    document.deleted_at = timezone.now()
    document.raw_text = ""
    document.clean_text = ""
    document.title = "Документ удалён"
    document.metadata_json = {}
    document.save(update_fields=["processing_status", "deleted_at", "raw_text", "clean_text", "title", "metadata_json", "updated_at"])
    write_audit(
        actor=actor,
        action="document_deleted",
        object_type="document",
        object_id=document.pk,
        before=before,
        after={"status": "deleted"},
        reason=reason,
        request=request,
    )
    from apps.analytics.services import rebuild_region_metrics

    for region_id in region_ids:
        rebuild_region_metrics(region_id)
    return document
