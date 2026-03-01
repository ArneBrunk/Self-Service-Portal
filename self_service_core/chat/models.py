# --- Import Django ---
from django.conf import settings
from django.db import models
from django.utils import timezone

# --- Models ---
class ChatSession(models.Model):
    STATUS_CHOICES = [
        ("open", "Offen"),
        ("done", "Erledigt"),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="open")
    greeting_sent = models.BooleanField(default=False)

    #Nutzerbewertung
    rating = models.PositiveSmallIntegerField(null=True, blank=True)  
    rating_text = models.TextField(blank=True)
    rated_at = models.DateTimeField(null=True, blank=True)

    def set_done(self):
        self.status = "done"
        self.save(update_fields=["status", "updated_at"])

    def __str__(self):
        return f"Session #{self.id} ({self.get_status_display()})"

class ChatMessage(models.Model):
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=16, choices=[("user","user"),("assistant","assistant"),("system","system")])
    content = models.TextField()
    sources = models.JSONField(default=list, blank=True)
    latency_ms = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)