from django import forms
from .models import CompanyProfile
from django import forms
from .models import CompanyProfile, ChatbotConfig
from django.contrib.auth import get_user_model

User = get_user_model()

class StaffProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "input"}),
            "last_name": forms.TextInput(attrs={"class": "input"}),
            "email": forms.EmailInput(attrs={"class": "input"}),
        }
class CompanyProfileForm(forms.ModelForm):
    class Meta:
        model = CompanyProfile
        fields = ["icon", "name", "description", "support_email", "support_phone"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "input"}),
            "description": forms.Textarea(attrs={"class": "input", "rows": 3}),
            "support_email": forms.EmailInput(attrs={"class": "input"}),
            "support_phone": forms.TextInput(attrs={"class": "input"}),
        }


class ChatbotConfigForm(forms.ModelForm):
    class Meta:
        model = ChatbotConfig
        fields = [
            "openai_api_key",
            "bot_name",
            "bot_role",
            "greeting_message",
            "conversation_tone",
            "response_length",
            "creativity_level",
            "confidence_threshold",
            "auto_escalation_enabled",
            "escalation_keywords",
            "proactive_help_enabled",
            "system_prompt_rag",
            "system_prompt_norag",
            "user_template_rag",
            "user_template_norag",
            "rag_default_enabled",
            "citations_default_required",
            "retrieval_top_k_default",
            "semantic_threshold_default",
            "semantic_method_default",
        ]
        widgets = {
            "openai_api_key": forms.PasswordInput(render_value=False, attrs={ "class": "input","placeholder": "••••••••••••••••",}),
            "bot_name": forms.TextInput(attrs={"class": "input"}),
            "bot_role": forms.TextInput(attrs={"class": "input"}),
            "system_prompt_rag": forms.Textarea(attrs={"class": "input", "rows": 10}),
            "system_prompt_norag": forms.Textarea(attrs={"class": "input", "rows": 10}),
            "user_template_rag": forms.Textarea(attrs={"class": "input", "rows": 6}),
            "user_template_norag": forms.Textarea(attrs={"class": "input", "rows": 6}),
            "semantic_method_default": forms.Select(attrs={"class": "input"}),
            "retrieval_top_k_default": forms.NumberInput(attrs={"class": "input", "min": 1, "max": 20}),
            "semantic_threshold_default": forms.NumberInput(attrs={"class": "input", "step": "0.01", "min": 0, "max": 1}),
            "greeting_message": forms.Textarea(attrs={"class": "input", "rows": 2}),
            "conversation_tone": forms.Select(attrs={"class": "input"}),
            "response_length": forms.Select(attrs={"class": "input"}),
            # sliders: wir benutzen type=range, Styling per CSS
            "creativity_level": forms.NumberInput(
                attrs={"class": "slider-input", "type": "range", "min": "0", "max": "1", "step": "0.01"}
            ),
            "confidence_threshold": forms.NumberInput(
                attrs={"class": "slider-input", "type": "range", "min": "0", "max": "100", "step": "1"}
            ),
            "escalation_keywords": forms.TextInput(
                attrs={"class": "input", "placeholder": "urgent, critical, refund"}
            ),
        }
