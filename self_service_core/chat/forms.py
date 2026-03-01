# --- Import Django ---
from django import forms


# --- Forms ---
class ChatForm(forms.Form):
    message = forms.CharField(
        label="Deine Frage",
        widget=forms.Textarea(attrs={
            "rows": 3,
            "placeholder": "Stelle hier deine Frage an den Support-Bot...",
        }),
    )
