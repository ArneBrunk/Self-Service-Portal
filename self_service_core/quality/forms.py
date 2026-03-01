from django import forms
from .models import EvalItem

class EvalItemForm(forms.ModelForm):
    class Meta:
        model = EvalItem
        fields = ["question", "expected_hint"]
        widgets = {
            "question": forms.Textarea(attrs={"rows": 3}),
            "expected_hint": forms.Textarea(attrs={"rows": 2}),
        }
