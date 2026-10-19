from __future__ import annotations

from rest_framework.permissions import BasePermission

SAFE = {"GET", "HEAD", "OPTIONS"}


class RolePermission(BasePermission):
    def has_permission(self, request, view) -> bool:
        user = request.user
        if not user.is_authenticated:
            return False
        if user.role == "admin":
            return True
        if user.role == "auditor" and request.method not in SAFE:
            return False
        action = getattr(view, "action", None)
        if action in {"confirm", "reject", "approve", "create"}:
            allowed = getattr(view, "write_roles", ())
            if action == "approve":
                allowed = ("approver",)
            return user.role in allowed
        if request.method not in SAFE:
            return user.role in getattr(view, "write_roles", ())
        return user.role in getattr(view, "read_roles", ())
