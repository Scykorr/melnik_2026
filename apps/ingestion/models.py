from __future__ import annotations

from django.db import models

from apps.common.models import TimeStampedModel


class IngestJob(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "В очереди"
        RUNNING = "running", "Выполняется"
        SUCCESS = "success", "Успех"
        ERROR = "error", "Ошибка"

    source = models.ForeignKey("sources.Source", on_delete=models.CASCADE, related_name="jobs")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    error_message = models.CharField(max_length=300, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    items_seen = models.PositiveIntegerField(default=0)
    items_created = models.PositiveIntegerField(default=0)
    items_skipped = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
