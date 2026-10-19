from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Администратор"
        OPERATOR = "operator", "Оператор"
        ANALYST = "analyst", "Аналитик"
        APPROVER = "approver", "Согласующий"
        AUDITOR = "auditor", "Аудитор"

    role = models.CharField("роль", max_length=20, choices=Role.choices, default=Role.ANALYST)
    mfa_enabled = models.BooleanField("MFA включена", default=False)
    mfa_secret = models.CharField("секрет MFA", max_length=64, blank=True)

    class Meta:
        verbose_name = "пользователь"
        verbose_name_plural = "пользователи"

    def __str__(self) -> str:
        return f"{self.username} ({self.get_role_display()})"
