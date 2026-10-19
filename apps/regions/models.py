from __future__ import annotations

from django.db import models

from apps.common.models import TimeStampedModel


class Region(TimeStampedModel):
    name = models.CharField("название", max_length=200)
    code = models.CharField("код", max_length=32, unique=True)
    parent = models.ForeignKey(
        "self",
        verbose_name="родитель",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="children",
    )
    is_active = models.BooleanField("активен", default=True)
    min_event_threshold = models.PositiveIntegerField(
        "порог агрегации, событий",
        default=1,
        help_text="Минимальное число подтверждённых событий для содержательного сравнения периода",
    )

    class Meta:
        verbose_name = "территория"
        verbose_name_plural = "территории"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Topic(TimeStampedModel):
    code = models.SlugField("код", max_length=64, unique=True)
    name = models.CharField("название", max_length=200)
    description = models.TextField("описание", blank=True)
    is_active = models.BooleanField("активна", default=True)
    rules_version = models.CharField("версия правил", max_length=64, default="topic-rules-1.0.0")

    class Meta:
        verbose_name = "тема требования"
        verbose_name_plural = "темы требований"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
