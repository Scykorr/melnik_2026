from __future__ import annotations

from rest_framework.authentication import SessionAuthentication


class SessionAuthentication401(SessionAuthentication):
    def authenticate_header(self, request):
        return "Session"
