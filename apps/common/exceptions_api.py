from __future__ import annotations

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler

from apps.common.exceptions import DomainError


def api_exception_handler(exc, context):
    request = context.get("request")
    request_id = getattr(request, "request_id", "")
    if isinstance(exc, DomainError):
        return Response(
            {"error": {"code": exc.code, "message": str(exc), "details": {}}, "request_id": request_id},
            status=exc.status_code,
        )
    if isinstance(exc, DjangoPermissionDenied):
        return Response(
            {
                "error": {"code": "permission_denied", "message": "Недостаточно прав", "details": {}},
                "request_id": request_id,
            },
            status=403,
        )
    if isinstance(exc, DjangoValidationError):
        return Response(
            {
                "error": {"code": "invalid", "message": "Данные не прошли проверку", "details": exc.message_dict if hasattr(exc, "message_dict") else exc.messages},
                "request_id": request_id,
            },
            status=400,
        )
    response = exception_handler(exc, context)
    if response is None:
        return Response(
            {
                "error": {"code": "server_error", "message": "Внутренняя ошибка", "details": {}},
                "request_id": request_id,
            },
            status=500,
        )
    message = "Запрос отклонён"
    if isinstance(response.data, dict) and "detail" in response.data:
        message = str(response.data["detail"])
    response.data = {
        "error": {"code": "request_error", "message": message, "details": response.data},
        "request_id": request_id,
    }
    return response
