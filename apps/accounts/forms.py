from django import forms
from django.contrib.auth.forms import UserCreationForm

from apps.accounts.models import User


class AccountCreateForm(UserCreationForm):
    role = forms.ChoiceField(choices=User.Role.choices, label="Роль")

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "role")
