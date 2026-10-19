from django import forms

from apps.sources.models import Source


class SourceForm(forms.ModelForm):
    class Meta:
        model = Source
        fields = [
            "name",
            "source_type",
            "base_url",
            "feed_url",
            "region_scope",
            "terms_url",
            "terms_checked_at",
            "collection_basis",
            "poll_interval",
            "reliability_weight",
            "is_active",
        ]
        widgets = {"terms_checked_at": forms.DateTimeInput(attrs={"type": "datetime-local"})}
