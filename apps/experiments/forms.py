from decimal import Decimal, InvalidOperation

from django import forms

from apps.experiments.models import StudyPackage, WorkSession


class WorkSessionForm(forms.ModelForm):
    class Meta:
        model = WorkSession
        fields = [
            "package",
            "analyst_code",
            "mode",
            "status",
            "documents_count",
            "events_count",
            "minutes_search",
            "minutes_clean",
            "minutes_dedup",
            "minutes_review",
            "minutes_calc",
            "minutes_writing",
            "minutes_corrections",
            "wait_background_minutes",
            "error_count",
            "missing_links",
            "date_errors",
            "false_inclusions",
            "completeness",
            "comparable",
            "incomparable_reason",
            "session_date",
        ]
        widgets = {"session_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["package"].queryset = StudyPackage.objects.all()

    def clean(self):
        cleaned = super().clean()
        completeness = cleaned.get("completeness")
        if completeness is not None and not 0 <= completeness <= 1:
            self.add_error("completeness", "Полнота задаётся от 0 до 1")
        if cleaned.get("status") == WorkSession.Status.COMPLETED and cleaned.get("comparable"):
            if cleaned.get("missing_links", 0):
                self.add_error("comparable", "Без ссылок на источники выпуск несопоставим")
            if completeness is not None and completeness < 0.9:
                self.add_error("comparable", "Низкая полнота блокирует интерпретацию ускорения")
        if cleaned.get("status") == WorkSession.Status.COMPLETED and not cleaned.get("comparable"):
            if not (cleaned.get("incomparable_reason") or "").strip():
                self.add_error("incomparable_reason", "Укажите, почему выпуск нельзя сравнивать")
        return cleaned


class EconomyForm(forms.Form):
    scenario = forms.ChoiceField(
        choices=[("conservative", "Консервативный прогноз"), ("base", "Базовый прогноз"), ("optimistic", "Оптимистичный прогноз")],
        label="Сценарий",
    )
    t0 = forms.DecimalField(label="T0, человеко-часы", min_value=0)
    t1 = forms.DecimalField(label="T1, человеко-часы", min_value=0)
    releases = forms.DecimalField(label="N, выпусков в год", min_value=0)
    hourly = forms.DecimalField(label="C, руб./час", min_value=0)
    operating = forms.DecimalField(label="C_op, руб./год", min_value=0)
    capex = forms.DecimalField(label="Первоначальные затраты, руб.", min_value=0, required=False)

    def result(self):
        from apps.experiments.calculations import economic_effect

        data = self.cleaned_data
        try:
            return economic_effect(
                t0=Decimal(data["t0"]),
                t1=Decimal(data["t1"]),
                releases=Decimal(data["releases"]),
                hourly=Decimal(data["hourly"]),
                operating=Decimal(data["operating"]),
                capex=Decimal(data["capex"]) if data.get("capex") is not None else None,
            )
        except (InvalidOperation, ZeroDivisionError):
            return None
