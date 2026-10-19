from __future__ import annotations

import hashlib
import re
import time
import uuid

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse

REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


class RequestIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.headers.get("X-Request-ID", "")
        request.request_id = incoming if REQUEST_ID_RE.match(incoming) else uuid.uuid4().hex
        response = self.get_response(request)
        response["X-Request-ID"] = request.request_id
        return response


class RateLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not settings.RATE_LIMIT_ENABLED:
            return self.get_response(request)
        ip = request.META.get("REMOTE_ADDR", "unknown")
        if request.path.startswith("/accounts/login") and request.method == "POST":
            if self._limited(f"login:{ip}", limit=10, window=300):
                return HttpResponse("Слишком много попыток входа. Повторите позже.", status=429)
        if request.path.startswith("/api/") and request.method not in {"GET", "HEAD", "OPTIONS"}:
            ident = request.user.pk if getattr(request.user, "is_authenticated", False) else ip
            if self._limited(f"api:{ident}", limit=60, window=60):
                return JsonResponse(
                    {
                        "error": {
                            "code": "rate_limited",
                            "message": "Превышен лимит запросов к API",
                            "details": {},
                        },
                        "request_id": getattr(request, "request_id", ""),
                    },
                    status=429,
                )
        return self.get_response(request)

    def _limited(self, key: str, limit: int, window: int) -> bool:
        now = time.time()
        bucket = cache.get(key, [])
        bucket = [stamp for stamp in bucket if now - stamp < window]
        if len(bucket) >= limit:
            cache.set(key, bucket, timeout=window)
            return True
        bucket.append(now)
        cache.set(key, bucket, timeout=window)
        return False


class ContentSecurityPolicyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not settings.DEBUG:
            response["Content-Security-Policy"] = (
                "default-src 'self'; img-src 'self' data:; style-src 'self'; "
                "script-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'self'; "
                "form-action 'self'"
            )
            response["Referrer-Policy"] = "same-origin"
            response["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response


def hash_ip(ip: str) -> str:
    if not ip:
        return ""
    payload = f"{settings.IP_HASH_SALT}|{ip}".encode()
    return hashlib.sha256(payload).hexdigest()
