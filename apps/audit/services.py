from __future__ import annotations

from apps.audit.models import AuditEntry
from apps.common.middleware import hash_ip


def write_audit(
    *,
    actor,
    action: str,
    object_type: str,
    object_id: str | int,
    before: dict | None = None,
    after: dict | None = None,
    reason: str = "",
    request=None,
) -> AuditEntry:
    request_id = ""
    ip_hash = ""
    if request is not None:
        request_id = getattr(request, "request_id", "") or ""
        ip_hash = hash_ip(request.META.get("REMOTE_ADDR", ""))
    return AuditEntry.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=action,
        object_type=object_type,
        object_id=str(object_id),
        before_json=before or {},
        after_json=after or {},
        reason=(reason or "")[:400],
        request_id=request_id,
        ip_hash=ip_hash,
    )
