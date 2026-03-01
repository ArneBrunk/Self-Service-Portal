# chat/forms.py
from django import forms

class ChatForm(forms.Form):
    message = forms.CharField(
        label="Deine Frage",
        widget=forms.Textarea(attrs={
            "rows": 3,
            "placeholder": "Stelle hier deine Frage an den Support-Bot...",
        }),
    )
