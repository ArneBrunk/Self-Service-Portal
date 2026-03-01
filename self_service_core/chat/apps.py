# --- Import Django ---
from django.apps import AppConfig


# --- Forms ---
class ChatConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'chat'
