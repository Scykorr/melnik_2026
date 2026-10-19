from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView

from apps.accounts.forms import AccountCreateForm
from apps.accounts.models import User
from apps.audit.services import write_audit
from apps.common.mixins import RoleRequiredMixin


class UserListView(RoleRequiredMixin, ListView):
    roles = ("admin",)
    model = User
    template_name = "accounts/users.html"
    context_object_name = "accounts"


class UserCreateView(RoleRequiredMixin, CreateView):
    roles = ("admin",)
    form_class = AccountCreateForm
    template_name = "accounts/user_form.html"
    success_url = reverse_lazy("users")

    def form_valid(self, form):
        response = super().form_valid(form)
        write_audit(
            actor=self.request.user,
            action="user_created",
            object_type="user",
            object_id=self.object.pk,
            after={"username": self.object.username, "role": self.object.role},
            request=self.request,
        )
        messages.success(self.request, "Учётная запись создана")
        return response
