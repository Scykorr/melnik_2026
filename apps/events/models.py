from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel


class Event(TimeStampedModel):
    class Status(models.TextChoices):
        NEW = "new", "Новое"
        IN_REVIEW = "in_review", "На проверке"
        NEEDS_INFO = "needs_info", "Нужны сведения"
        CONFIRMED = "confirmed", "Подтверждено"
        REJECTED = "rejected", "Отклонено"
        ARCHIVED = "archived", "Архив"

    region = models.ForeignKey("regions.Region", verbose_name="территория", on_delete=models.PROTECT, related_name="events")
    occurred_at = models.DateTimeField("время события")
    topic = models.ForeignKey("regions.Topic", verbose_name="основная тема", on_delete=models.PROTECT, related_name="events")
    title = models.CharField("заголовок", max_length=400)
    summary = models.TextField("краткое описание", blank=True)
    status = models.CharField("статус", max_length=20, choices=Status.choices, default=Status.NEW)
    scale_score = models.FloatField("масштаб", default=0.4)
    relevance_score = models.FloatField("релевантность", default=0)
    confidence = models.FloatField("уверенность", default=0)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="проверил",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_events",
    )
    reviewed_at = models.DateTimeField("проверено", null=True, blank=True)
    review_comment = models.TextField("комментарий проверки", blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="назначен",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_events",
    )
    grouping_explanation = models.TextField("объяснение группировки", blank=True)

    class Meta:
        verbose_name = "событие"
        verbose_name_plural = "события"
        ordering = ["-occurred_at"]
        indexes = [models.Index(fields=["status", "occurred_at"]), models.Index(fields=["region", "status"])]

    def __str__(self) -> str:
        return self.title


class EventDocument(models.Model):
    class RelationType(models.TextChoices):
        PRIMARY = "primary", "Первоисточник"
        REPRINT = "reprint", "Перепечатка"
        CONTEXT = "context", "Контекст"

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="links")
    document = models.ForeignKey("documents.Document", on_delete=models.PROTECT, related_name="links")
    relation_type = models.CharField(max_length=20, choices=RelationType.choices, default=RelationType.PRIMARY)
    is_primary = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["event", "document"], name="uniq_event_document")]


class EventTopic(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="topics")
    topic = models.ForeignKey("regions.Topic", on_delete=models.PROTECT, related_name="event_links")
    is_primary = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["event", "topic"], name="uniq_event_topic")]


class EventDecision(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="decisions")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    from_status = models.CharField(max_length=20)
    to_status = models.CharField(max_length=20)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class Assessment(models.Model):
    event = models.ForeignKey(Event, null=True, blank=True, on_delete=models.CASCADE, related_name="assessments")
    document = models.ForeignKey(
        "documents.Document", null=True, blank=True, on_delete=models.CASCADE, related_name="assessments"
    )
    model_name = models.CharField(max_length=80)
    model_version = models.CharField(max_length=80)
    label = models.CharField(max_length=80)
    score = models.FloatField(default=0)
    confidence = models.FloatField(default=0)
    explanation_json = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
