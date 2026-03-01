# --- Import Django ---
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings
from django_cryptography.fields import encrypt
# --- Import App-Content ---
from .utils import generate_favicon_from_logo

# --- Models ---
class StaffUser(models.Model):
    ROLE_CHOICES = [
        ("employee", "Mitarbeiter"),
        ("admin", "Administrator"),
    ]
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="staff",
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    department = models.CharField(max_length=120, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} ({self.get_role_display()})"

class CompanyProfile(models.Model):
    """Branding für das Portal und den Chatbot."""
    name = models.CharField("Company Name", max_length=255, default="Your Company")
    description = models.TextField("Company Description", blank=True)
    icon = models.ImageField("Company Icon", upload_to="company_icons/", blank=True, null=True)
    support_email = models.EmailField("Support Email", blank=True)
    support_phone = models.CharField("Support Phone", max_length=64, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="companyprofile_updated",
    )
    def __str__(self):
        return self.name

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(id=1)
        return obj
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Favicon generieren sobald ein Logo existiert
        if self.icon:
            generate_favicon_from_logo(self.icon)
    
class ChatbotConfig(models.Model):
    """Steuert Verhalten & Persönlichkeit des Bots."""
    TONE_CHOICES = [
        ("professional", "Professional"),
        ("friendly", "Friendly"),
        ("casual", "Casual"),
    ]
    RESPONSE_LENGTH_CHOICES = [
        ("short", "Short"),
        ("moderate", "Moderate"),
        ("detailed", "Detailed"),
    ]
    openai_api_key = encrypt(models.CharField(
        max_length=200,
        blank=True,
        help_text="API-Key für ChatGPT (wird verschlüsselt gespeichert)."
    ))
    bot_name = models.CharField(max_length=100, default="Support Bot")
    bot_role = models.CharField(max_length=200, default="Customer Support Assistant")
    system_prompt_rag = models.TextField(blank=True, default="")
    system_prompt_norag = models.TextField(blank=True, default="")
    user_template_rag = models.TextField(blank=True, default="")
    user_template_norag = models.TextField(blank=True, default="")
    greeting_message = models.TextField(
        default="Hello! I'm your support assistant. How can I help you today?"
    )
    rag_default_enabled = models.BooleanField(default=True)
    citations_default_required = models.BooleanField(default=True)

    retrieval_top_k_default = models.IntegerField(default=6)
    semantic_threshold_default = models.FloatField(default=0.80)
    semantic_method_default = models.CharField(
        max_length=20, choices=[("v1","V1 (Coverage)"),("v2","V2 (Hybrid)"),("legacy","Legacy")],
        default="v1"
    )
    conversation_tone = models.CharField(
        max_length=32, choices=TONE_CHOICES, default="professional"
    )
    response_length = models.CharField(
        max_length=32, choices=RESPONSE_LENGTH_CHOICES, default="moderate"
    )
    creativity_level = models.FloatField(
        default=0.3,
        help_text="Temperature between 0.0 (focused) and 1.0 (creative).",
    )
    confidence_threshold = models.IntegerField(
        default=75,
        help_text="Percent. Below this, conversation may be escalated.",
    )
    auto_escalation_enabled = models.BooleanField(default=True)
    escalation_keywords = models.TextField(
        blank=True,
        help_text="Comma-separated keywords that should trigger escalation (e.g. urgent,critical,refund).",
    )
    proactive_help_enabled = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="chatbotconfig_updated",
    )

    def __str__(self):
        return f"ChatbotConfig ({self.bot_name})"

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(id=1)
        return obj
    def escalation_keywords_list(self) -> list[str]:
        if not self.escalation_keywords:
            return []
        return [kw.strip().lower() for kw in self.escalation_keywords.split(",") if kw.strip()]