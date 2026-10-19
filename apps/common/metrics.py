from __future__ import annotations

from django.http import HttpResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

HTTP_REQUESTS = Counter(
    "iam_http_requests_total",
    "Число HTTP-запросов без персональных меток",
    ["method", "status"],
)
HTTP_LATENCY = Histogram(
    "iam_http_request_seconds",
    "Длительность HTTP-запроса",
    ["method"],
)


class MetricsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/metrics"):
            return self.get_response(request)
        with HTTP_LATENCY.labels(method=request.method).time():
            response = self.get_response(request)
        HTTP_REQUESTS.labels(method=request.method, status=str(response.status_code)).inc()
        return response


def metrics_view(request):
    return HttpResponse(generate_latest(), content_type=CONTENT_TYPE_LATEST)
