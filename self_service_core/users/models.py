# --- Import Django ---
from django.contrib.auth.models import AbstractUser
from django.db import models


# --- Models ---
class ServicePlan(models.Model):
    """
    Service-Level für Kunden: free, premium, pro, etc.
    """
    code = models.CharField(max_length=20, unique=True)  
    name = models.CharField(max_length=50)               
    description = models.TextField(blank=True)
    max_daily_messages = models.IntegerField(default=50)
    max_monthly_messages = models.IntegerField(default=500)
    priority_support = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.name} ({self.code})"


class User(AbstractUser):
    """
    Zentrales Login-Modell.
    """
    pass


class Customer(models.Model):
    """
    Kundentabelle – 1:1 zum User.
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="customer",
    )
    customer_id = models.CharField(
        max_length=20,
        unique=True,
        help_text="Interne Kundennummer (z. B. K-000001).",
    )
    service_plan = models.ForeignKey(
        ServicePlan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customers",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.customer_id} – {self.user.get_full_name() or self.user.username}"
