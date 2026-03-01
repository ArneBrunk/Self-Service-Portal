from django.db import models
from django_cryptography.fields import encrypt
from solo.models import SingletonModel
from chat.models import ChatSession


class Ticket(models.Model):
    STATUS_CHOICES = [
        ("escalated", "Escalated"),
        ("in_progress", "In Progress"),
        ("solved", "Solved"),
    ]

    PRIORITY_CHOICES = [
        ("high", "HIGH"),
        ("medium", "MEDIUM"),
        ("low", "LOW"),
    ]
    exported = models.BooleanField(
        default=False,
        help_text="Wurde dieses Ticket bereits an das externe Ticket-System übertragen?"
    )
    external_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="ID des Tickets im externen System"
    )
    exported_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Zeitpunkt der letzten erfolgreichen Übertragung"
    )
    title = models.CharField(max_length=255)
    customer = models.ForeignKey(
        "users.Customer",
        on_delete=models.PROTECT,      # verhindert Löschen eines Customers, wenn Tickets existieren
        related_name="tickets",
        null=False,
        blank=False,
    )

    customer_name = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="in_progress")
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default="medium")
    created_at = models.DateTimeField(auto_now_add=True)
    session = models.ForeignKey(ChatSession, on_delete=models.SET_NULL,null=True, blank=True, related_name="tickets")


    def __str__(self):
        return self.title

class TicketSystemConfig(SingletonModel):
    """
    Konfiguration für externes Ticketsystem (z. B. Jira, Freshdesk, Zendesk, etc.)
    Wird im Staff-Admin eingestellt.
    """

    enabled = models.BooleanField(default=False)

    api_url = models.URLField(
        blank=True,
        help_text="Basis-URL des Ticket-Systems, z. B. https://api.freshdesk.com/v2/tickets"
    )

    api_key = encrypt(models.CharField(
        max_length=200,
        blank=True,
        help_text="API-Key für das Ticket-System (verschlüsselt gespeichert)"
    ))

    api_format = models.CharField(
        max_length=50,
        default="json-default",
        help_text="Format des JSON-Bodies (für spätere Erweiterungen)"
    )

    def __str__(self):
        return "Ticket System Configuration"