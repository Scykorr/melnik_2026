from __future__ import annotations

from django.db import models

from apps.common.models import TimeStampedModel


class DailyMetric(TimeStampedModel):
    region = models.ForeignKey("regions.Region", on_delete=models.CASCADE, related_name="metrics")
    date = models.DateField()
    index_value = models.FloatField(null=True, blank=True)
    event_count = models.PositiveIntegerField(default=0)
    independent_source_count = models.PositiveIntegerField(default=0)
    review_coverage = models.FloatField(default=0)
    method_version = models.CharField(max_length=64)
    components_json = models.JSONField(default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["region", "date", "method_version"],
                name="uniq_metric_region_date_method",
            )
        ]
        ordering = ["date"]
