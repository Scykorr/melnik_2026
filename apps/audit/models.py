from __future__ import annotations

from django.conf import settings
from django.db import models


class AuditEntry(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=80)
    object_type = models.CharField(max_length=80)
    object_id = models.CharField(max_length=64)
    before_json = models.JSONField(default=dict)
    after_json = models.JSONField(default=dict)
    reason = models.CharField(max_length=400, blank=True)
    request_id = models.CharField(max_length=64, blank=True)
    ip_hash = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["object_type", "object_id"]), models.Index(fields=["action"])]

    def __str__(self) -> str:
        return f"{self.action} {self.object_type}:{self.object_id}"
