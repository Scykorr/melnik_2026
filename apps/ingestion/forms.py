from django import forms

from apps.sources.models import Source


class ManualUrlForm(forms.Form):
    source = forms.ModelChoiceField(queryset=Source.objects.filter(is_active=True), label="Источник")
    url = forms.URLField(label="Публичная ссылка", assume_scheme="https")
    title = forms.CharField(label="Заголовок", max_length=400, required=False)
    text = forms.CharField(label="Текст, если уже скопирован", widget=forms.Textarea, required=False)
    published_at = forms.DateTimeField(
        label="Дата публикации",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )


class ImportForm(forms.Form):
    source = forms.ModelChoiceField(queryset=Source.objects.none(), label="Источник")
    upload = forms.FileField(label="JSON или CSV")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["source"].queryset = Source.objects.filter(is_active=True)
