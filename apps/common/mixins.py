from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

SAFE = {"GET", "HEAD", "OPTIONS"}


class RoleRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    roles: tuple[str, ...] = ()
    raise_exception = True

    def test_func(self) -> bool:
        user = self.request.user
        if user.role == "admin":
            return True
        if user.role == "auditor" and self.request.method not in SAFE:
            return False
        return user.role in self.roles

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect_to_login(self.request.get_full_path(), self.get_login_url(), self.get_redirect_field_name())
        raise PermissionDenied(self.get_permission_denied_message())
