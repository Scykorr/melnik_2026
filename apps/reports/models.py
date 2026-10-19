from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.common.exceptions import ImmutableReportError


class Report(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        IN_REVIEW = "in_review", "На согласовании"
        APPROVED = "approved", "Утверждён"
        PUBLISHED = "published", "Опубликован"

    region = models.ForeignKey("regions.Region", on_delete=models.PROTECT, related_name="reports")
    period_start = models.DateField()
    period_end = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    version = models.PositiveIntegerField(default=1)
    title = models.CharField(max_length=400)
    executive_summary = models.TextField(blank=True)
    body_json = models.JSONField(default=dict)
    input_hash = models.CharField(max_length=64)
    template_version = models.CharField(max_length=32, default="iam-template-1.0.0")
    method_version = models.CharField(max_length=64, default="ipa-1.0.0")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_reports"
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_reports",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    file = models.FileField(upload_to="reports/", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "ИАМ"
        verbose_name_plural = "ИАМ"

    def __str__(self) -> str:
        return f"{self.title} v{self.version}"

    def save(self, *args, **kwargs):
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).values_list("status", flat=True).first()
            if previous in {self.Status.APPROVED, self.Status.PUBLISHED}:
                raise ImmutableReportError("Утверждённую версию отчёта нельзя изменять")
        super().save(*args, **kwargs)
