from __future__ import annotations

from datetime import timedelta

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from apps.audit.services import write_audit
from apps.common.exceptions import TransitionError
from apps.documents.dedup import should_merge_texts
from apps.documents.models import Document
from apps.events.models import Assessment, Event, EventDecision, EventDocument, EventTopic

ALLOWED: dict[str, set[str]] = {
    Event.Status.NEW: {Event.Status.IN_REVIEW, Event.Status.REJECTED, Event.Status.ARCHIVED},
    Event.Status.IN_REVIEW: {
        Event.Status.NEEDS_INFO,
        Event.Status.CONFIRMED,
        Event.Status.REJECTED,
        Event.Status.ARCHIVED,
    },
    Event.Status.NEEDS_INFO: {Event.Status.IN_REVIEW, Event.Status.REJECTED, Event.Status.ARCHIVED},
    Event.Status.CONFIRMED: {Event.Status.ARCHIVED},
    Event.Status.REJECTED: {Event.Status.ARCHIVED},
    Event.Status.ARCHIVED: set(),
}
COMMENT_REQUIRED = {Event.Status.CONFIRMED, Event.Status.REJECTED, Event.Status.NEEDS_INFO}
REVIEW_ROLES = {"analyst", "admin"}


def _scale(text: str) -> float:
    low = (text or "").lower()
    if "забастов" in low or "шеств" in low:
        return 0.8
    if "митинг" in low or "пикет" in low or "собрани" in low:
        return 0.6
    return 0.4


@transaction.atomic
def propose_event_for_document(document: Document) -> Event | None:
    if document.processing_status != Document.ProcessingStatus.PROCESSED:
        return None
    if document.relevance_label != Document.RelevanceLabel.RELEVANT:
        return None
    if document.deleted_at or not document.primary_topic_id or document.published_at is None:
        return None
    region = document.source.region_scope
    if region is None:
        return None
    linked = EventDocument.objects.filter(document=document).select_related("event").first()
    if linked:
        return linked.event
    window = timedelta(hours=36)
    candidates = Event.objects.filter(
        region=region,
        topic=document.primary_topic,
        status__in=[Event.Status.NEW, Event.Status.IN_REVIEW, Event.Status.NEEDS_INFO, Event.Status.CONFIRMED],
        occurred_at__range=(document.published_at - window, document.published_at + window),
    )
    fact_code = str((document.metadata_json or {}).get("fact_code") or "")
    for event in candidates:
        primary = (
            event.links.filter(is_primary=True).select_related("document").first()
            or event.links.select_related("document").first()
        )
        if primary is None:
            continue
        other_fact = str((primary.document.metadata_json or {}).get("fact_code") or "")
        merged, _score, explanation = should_merge_texts(
            primary.document.clean_text or primary.document.title,
            document.clean_text or document.title,
            left_fact=other_fact,
            right_fact=fact_code,
        )
        if merged:
            EventDocument.objects.get_or_create(
                event=event,
                document=document,
                defaults={"relation_type": EventDocument.RelationType.REPRINT, "is_primary": False},
            )
            event.grouping_explanation = explanation
            event.save(update_fields=["grouping_explanation", "updated_at"])
            return event
    event = Event.objects.create(
        region=region,
        occurred_at=document.published_at,
        topic=document.primary_topic,
        title=document.title[:400],
        summary=(document.clean_text or "")[:700],
        status=Event.Status.NEW,
        scale_score=_scale(document.clean_text),
        relevance_score=document.relevance_confidence,
        confidence=document.relevance_confidence,
        grouping_explanation="Новое событие: не найдено совпадения времени, территории и фактов требования.",
    )
    EventDocument.objects.create(
        event=event,
        document=document,
        relation_type=EventDocument.RelationType.PRIMARY,
        is_primary=True,
    )
    for code in document.topic_codes or [document.primary_topic.code]:
        topic = document.primary_topic if code == document.primary_topic.code else None
        if topic is None:
            from apps.regions.models import Topic

            topic = Topic.objects.filter(code=code).first()
        if topic is None:
            continue
        EventTopic.objects.get_or_create(
            event=event,
            topic=topic,
            defaults={"is_primary": topic.pk == document.primary_topic_id},
        )
    Assessment.objects.create(
        event=event,
        document=document,
        model_name="rule-classifier",
        model_version=document.rule_or_model_version,
        label=document.relevance_label,
        score=document.relevance_score if hasattr(document, "relevance_score") else document.relevance_confidence,
        confidence=document.relevance_confidence,
        explanation_json={"basis": document.classification_basis, "topics": document.topic_codes},
    )
    return event


def set_primary_topic(*, event: Event, topic, actor, request=None) -> Event:
    if actor.role not in REVIEW_ROLES:
        raise PermissionDenied
    if event.reviewed_by_id and event.status in {Event.Status.CONFIRMED, Event.Status.REJECTED}:
        raise TransitionError("Решение аналитика уже зафиксировано")
    event.topic = topic
    event.save(update_fields=["topic", "updated_at"])
    EventTopic.objects.update_or_create(event=event, topic=topic, defaults={"is_primary": True})
    EventTopic.objects.filter(event=event).exclude(topic=topic).update(is_primary=False)
    write_audit(
        actor=actor,
        action="event_topic_changed",
        object_type="event",
        object_id=event.pk,
        after={"topic": topic.code},
        request=request,
    )
    return event


@transaction.atomic
def transition_event(*, event: Event, new_status: str, actor, comment: str = "", request=None) -> Event:
    if actor.role not in REVIEW_ROLES:
        raise PermissionDenied
    if actor.role != "admin" and event.assigned_to_id not in (None, actor.id):
        raise PermissionDenied
    locked = Event.objects.select_for_update().get(pk=event.pk)
    if new_status not in ALLOWED.get(locked.status, set()):
        raise TransitionError(f"Переход {locked.status} → {new_status} не допускается")
    comment = (comment or "").strip()
    if new_status in COMMENT_REQUIRED and len(comment) < 3:
        raise TransitionError("Для этого решения нужен комментарий")
    before = {"status": locked.status}
    EventDecision.objects.create(
        event=locked,
        actor=actor,
        from_status=locked.status,
        to_status=new_status,
        comment=comment,
    )
    locked.status = new_status
    if comment:
        locked.review_comment = comment
    if new_status in {Event.Status.CONFIRMED, Event.Status.REJECTED, Event.Status.NEEDS_INFO}:
        locked.reviewed_by = actor
        locked.reviewed_at = timezone.now()
    locked.save()
    write_audit(
        actor=actor,
        action="event_status_changed",
        object_type="event",
        object_id=locked.pk,
        before=before,
        after={"status": new_status},
        reason=comment,
        request=request,
    )
    if new_status in {Event.Status.CONFIRMED, Event.Status.ARCHIVED, Event.Status.REJECTED}:
        from apps.analytics.services import rebuild_region_metrics

        rebuild_region_metrics(locked.region_id)
    return locked


@transaction.atomic
def assign_events(*, event_ids: list[int], assignee, actor, request=None) -> int:
    if actor.role not in REVIEW_ROLES:
        raise PermissionDenied
    if assignee.role not in REVIEW_ROLES:
        raise TransitionError("Назначать можно только аналитика")
    count = 0
    for event in Event.objects.select_for_update().filter(pk__in=event_ids):
        before = {"assigned_to": event.assigned_to_id, "status": event.status}
        event.assigned_to = assignee
        if event.status == Event.Status.NEW:
            event.status = Event.Status.IN_REVIEW
            EventDecision.objects.create(
                event=event,
                actor=actor,
                from_status=Event.Status.NEW,
                to_status=Event.Status.IN_REVIEW,
                comment="Назначено аналитику",
            )
        event.save()
        write_audit(
            actor=actor,
            action="event_assigned",
            object_type="event",
            object_id=event.pk,
            before=before,
            after={"assigned_to": assignee.pk, "status": event.status},
            request=request,
        )
        count += 1
    return count


def record_assessment(*, event: Event, label: str, score: float, confidence: float, explanation: dict) -> Assessment:
    assessment = Assessment.objects.create(
        event=event,
        model_name="rule-classifier",
        model_version="relevance-rules-1.0.0",
        label=label,
        score=score,
        confidence=confidence,
        explanation_json=explanation,
    )
    if event.reviewed_by_id:
        return assessment
    event.relevance_score = score
    event.confidence = confidence
    event.save(update_fields=["relevance_score", "confidence", "updated_at"])
    return assessment
