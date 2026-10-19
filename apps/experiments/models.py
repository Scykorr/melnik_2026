from __future__ import annotations

from django.db import models

from apps.common.models import TimeStampedModel


class GoldDocumentLabel(TimeStampedModel):
    dataset = models.CharField(max_length=120)
    document_uid = models.CharField(max_length=64)
    relevance = models.CharField(max_length=20)
    topic_code = models.CharField(max_length=64, blank=True)
    region_code = models.CharField(max_length=32, blank=True)
    event_group_id = models.CharField(max_length=64, blank=True)
    rules_version = models.CharField(max_length=64)
    split = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=20, default="active")
    text = models.TextField(blank=True)
    published_on = models.DateField(null=True, blank=True)
    dataset_kind = models.CharField(max_length=20, default="external")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["dataset", "document_uid"], name="uniq_gold_document"),
        ]


class GoldEventGroup(TimeStampedModel):
    dataset = models.CharField(max_length=120)
    event_group_id = models.CharField(max_length=64)
    region_code = models.CharField(max_length=32, blank=True)
    topic_code = models.CharField(max_length=64, blank=True)
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["dataset", "event_group_id"], name="uniq_gold_group"),
        ]


class EvaluationRun(models.Model):
    dataset = models.CharField(max_length=120)
    dataset_kind = models.CharField(max_length=20, default="external")
    method = models.CharField(max_length=40)
    method_version = models.CharField(max_length=80)
    split = models.CharField(max_length=20)
    parameters = models.JSONField(default=dict)
    sample_size = models.PositiveIntegerField(default=0)
    candidate_count = models.PositiveIntegerField(default=0)
    true_positive = models.PositiveIntegerField(default=0)
    false_positive = models.PositiveIntegerField(default=0)
    false_negative = models.PositiveIntegerField(default=0)
    precision = models.FloatField(null=True, blank=True)
    recall = models.FloatField(null=True, blank=True)
    f1 = models.FloatField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(default=0)
    environment = models.JSONField(default=dict)
    unreliable = models.BooleanField(default=False)
    warning = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class StudyPackage(TimeStampedModel):
    code = models.CharField(max_length=64, unique=True)
    title = models.CharField(max_length=300)
    document_count = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)


class WorkSession(TimeStampedModel):
    class Mode(models.TextChoices):
        AS_IS = "as_is", "AS-IS, ручной режим"
        TO_BE = "to_be", "TO-BE, с системой"

    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        COMPLETED = "completed", "Завершена"

    package = models.ForeignKey(StudyPackage, on_delete=models.CASCADE, related_name="sessions")
    analyst_code = models.CharField("анонимный код аналитика", max_length=32)
    mode = models.CharField(max_length=16, choices=Mode.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    documents_count = models.PositiveIntegerField(default=0)
    events_count = models.PositiveIntegerField(default=0)
    minutes_search = models.PositiveIntegerField(default=0)
    minutes_clean = models.PositiveIntegerField(default=0)
    minutes_dedup = models.PositiveIntegerField(default=0)
    minutes_review = models.PositiveIntegerField(default=0)
    minutes_calc = models.PositiveIntegerField(default=0)
    minutes_writing = models.PositiveIntegerField(default=0)
    minutes_corrections = models.PositiveIntegerField(default=0)
    wait_background_minutes = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    missing_links = models.PositiveIntegerField(default=0)
    date_errors = models.PositiveIntegerField(default=0)
    false_inclusions = models.PositiveIntegerField(default=0)
    completeness = models.FloatField(null=True, blank=True)
    comparable = models.BooleanField(default=False)
    incomparable_reason = models.CharField(max_length=400, blank=True)
    app_version = models.CharField(max_length=32, blank=True)
    session_date = models.DateField()

    class Meta:
        ordering = ["-session_date", "analyst_code"]

    @property
    def human_active_minutes(self) -> int:
        return (
            self.minutes_search
            + self.minutes_clean
            + self.minutes_dedup
            + self.minutes_review
            + self.minutes_calc
            + self.minutes_writing
            + self.minutes_corrections
        )


class StudyResult(TimeStampedModel):
    """Сохранённый снимок сопоставления. Фактические цифры появляются только из завершённых сессий."""

    package = models.ForeignKey(StudyPackage, on_delete=models.CASCADE, related_name="results")
    pair_count = models.PositiveIntegerField(default=0)
    median_k_t = models.FloatField(null=True, blank=True)
    min_k_t = models.FloatField(null=True, blank=True)
    max_k_t = models.FloatField(null=True, blank=True)
    saved_hours = models.FloatField(null=True, blank=True)
    status_label = models.CharField(max_length=40, default="не измерено")
    note = models.CharField(max_length=400, blank=True)
