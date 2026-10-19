from django import forms


class ReportCreateForm(forms.Form):
    title = forms.CharField(max_length=400, label="Заголовок")
    region = forms.ModelChoiceField(queryset=None, label="Территория")
    period_start = forms.DateField(label="Начало", widget=forms.DateInput(attrs={"type": "date"}))
    period_end = forms.DateField(label="Конец", widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, **kwargs):
        from apps.regions.models import Region

        super().__init__(*args, **kwargs)
        self.fields["region"].queryset = Region.objects.filter(is_active=True)


class ReportDraftForm(forms.Form):
    executive_summary = forms.CharField(label="Резюме аналитика", widget=forms.Textarea, required=False)
    summary = forms.CharField(label="Утверждённый текст: резюме", widget=forms.Textarea, required=False)
    topics = forms.CharField(label="Утверждённый текст: темы", widget=forms.Textarea, required=False)
    dynamics = forms.CharField(label="Утверждённый текст: динамика", widget=forms.Textarea, required=False)
    facts = forms.CharField(label="Утверждённый текст: факты", widget=forms.Textarea, required=False)
    limitations = forms.CharField(label="Утверждённый текст: ограничения", widget=forms.Textarea, required=False)
