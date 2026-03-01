# --- Import Django ---
from django import forms
# --- Import App-Content ---
from .models import EvalItem

# --- Forms ---
class EvalItemForm(forms.ModelForm):
    class Meta:
        model = EvalItem
        fields = ["question", "expected_hint"]
        widgets = {
            "question": forms.Textarea(attrs={"rows": 3}),
            "expected_hint": forms.Textarea(attrs={"rows": 2}),
        }
