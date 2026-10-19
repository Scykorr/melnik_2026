from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models

from apps.common.models import TimeStampedModel


class Source(TimeStampedModel):
    class SourceType(models.TextChoices):
        RSS = "rss", "RSS"
        ATOM = "atom", "Atom"
        JSON = "json", "JSON"
        CSV = "csv", "CSV"
        MANUAL = "manual", "Ручная ссылка"
        OFFICIAL_API = "official_api", "Официальный API"

    name = models.CharField("название", max_length=200)
    source_type = models.CharField("тип", max_length=32, choices=SourceType.choices)
    base_url = models.URLField("базовый URL", max_length=500)
    feed_url = models.CharField("адрес ленты или файла", max_length=500, blank=True)
    region_scope = models.ForeignKey(
        "regions.Region",
        verbose_name="территория охвата",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="sources",
    )
    terms_url = models.URLField("условия использования", max_length=500)
    terms_checked_at = models.DateTimeField("условия проверены", null=True, blank=True)
    collection_basis = models.TextField("основание сбора")
    poll_interval = models.PositiveIntegerField("интервал опроса, минуты", default=60)
    reliability_weight = models.FloatField("вес надёжности", default=0.5)
    is_active = models.BooleanField("активен", default=True)
    last_success_at = models.DateTimeField("последний успех", null=True, blank=True)
    last_error = models.CharField("последняя ошибка", max_length=300, blank=True)

    class Meta:
        verbose_name = "источник"
        verbose_name_plural = "источники"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        if not (self.collection_basis or "").strip():
            raise ValidationError({"collection_basis": "Укажите основание сбора открытых данных"})
        if not self.terms_url:
            raise ValidationError({"terms_url": "Укажите адрес условий использования"})
        if self.is_active and self.terms_checked_at is None:
            raise ValidationError({"terms_checked_at": "Активный источник требует отметки о проверке условий"})
        if not 0 <= self.reliability_weight <= 1:
            raise ValidationError({"reliability_weight": "Вес должен быть от 0 до 1"})
