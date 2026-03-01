# --- Import Django ---
from django import forms
# --- Models ---
from .models import TicketSystemConfig

# --- Forms ---
# 
class TicketSystemConfigForm(forms.ModelForm):
    class Meta:
        model = TicketSystemConfig
        fields = [
            "enabled",
            "api_url",
            "api_key",
            "api_format",
        ]
        widgets = {
            "enabled": forms.CheckboxInput(attrs={"class": "checkbox"}),
            "api_key": forms.PasswordInput(render_value=False, attrs={ "class": "input","placeholder": "••••••••••••••••",}),
            "api_url": forms.URLInput(attrs={"class": "input"}),
            "api_format": forms.TextInput(attrs={"class": "input"}),
        }