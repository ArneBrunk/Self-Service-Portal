# --- Import Django ---
from django.db.models.signals import post_save
from django.dispatch import receiver

# --- Import App-Content ---
from users.models import User
from .models import StaffUser



# ---  Helper-Funktionen ---
@receiver(post_save, sender=User)
def ensure_superuser_has_staff_profile(sender, instance: User, created, **kwargs):
    """
    Immer wenn ein User gespeichert wird:
    - Falls er superuser ist,
      bekommt er automatisch ein StaffUser-Profil als Admin.
    """
    if instance.is_superuser:
        StaffUser.objects.get_or_create(
            user=instance,
            defaults={"role": "admin", "is_active": True},
        )
