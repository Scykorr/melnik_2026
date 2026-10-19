from __future__ import annotations

from django.db import models

from apps.common.models import TimeStampedModel


class Document(TimeStampedModel):
    class ProcessingStatus(models.TextChoices):
        PENDING = "pending", "Ожидает"
        PROCESSED = "processed", "Обработан"
        DUPLICATE = "duplicate", "Точный дубль"
        QUARANTINE = "quarantine", "Карантин"
        DELETED = "deleted", "Удалён"

    class RelevanceLabel(models.TextChoices):
        RELEVANT = "relevant", "Релевантен"
        IRRELEVANT = "irrelevant", "Нерелевантен"
        UNCERTAIN = "uncertain", "Спорно"
        UNCLASSIFIED = "unclassified", "Не классифицирован"

    source = models.ForeignKey("sources.Source", verbose_name="источник", on_delete=models.PROTECT, related_name="documents")
    canonical_url = models.CharField("канонический URL", max_length=1000)
    title = models.CharField("заголовок", max_length=400)
    published_at = models.DateTimeField("опубликовано", null=True, blank=True)
    fetched_at = models.DateTimeField("загружено")
    language = models.CharField("язык", max_length=12, default="ru")
    raw_text = models.TextField("исходный текст", blank=True)
    clean_text = models.TextField("очищенный текст", blank=True)
    checksum = models.CharField("контрольная сумма", max_length=64, db_index=True)
    metadata_json = models.JSONField("метаданные", default=dict, blank=True)
    processing_status = models.CharField(
        "статус обработки",
        max_length=20,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.PENDING,
    )
    deleted_at = models.DateTimeField("удалён", null=True, blank=True)
    relevance_label = models.CharField(
        "релевантность",
        max_length=20,
        choices=RelevanceLabel.choices,
        default=RelevanceLabel.UNCLASSIFIED,
    )
    relevance_confidence = models.FloatField("уверенность релевантности", default=0)
    rule_or_model_version = models.CharField("версия правил", max_length=120, blank=True)
    classification_basis = models.TextField("основание классификации", blank=True)
    primary_topic = models.ForeignKey(
        "regions.Topic",
        verbose_name="основная тема",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="documents",
    )
    topic_codes = models.JSONField("коды тем", default=list, blank=True)
    quarantine_reason = models.CharField("причина карантина", max_length=300, blank=True)
    normalized_title = models.CharField("нормализованный заголовок", max_length=400, blank=True, db_index=True)
    duplicate_of = models.ForeignKey(
        "self",
        verbose_name="точный оригинал",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="exact_duplicates",
    )

    class Meta:
        verbose_name = "документ"
        verbose_name_plural = "документы"
        constraints = [
            models.UniqueConstraint(fields=["source", "canonical_url"], name="uniq_source_canonical_url"),
        ]
        indexes = [
            models.Index(fields=["checksum"]),
            models.Index(fields=["normalized_title", "published_at"]),
        ]

    def __str__(self) -> str:
        return self.title
