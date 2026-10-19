from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse


def live(_request):
    return JsonResponse({"status": "ok"})


def ready(_request):
    try:
        connection.ensure_connection()
        cache.set("iam-ready", "1", 5)
        if cache.get("iam-ready") != "1":
            raise RuntimeError("cache")
    except Exception:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})
