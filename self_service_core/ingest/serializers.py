# --- Import Django ---
from rest_framework import serializers

# --- Import App-Content ---
from knowledge.models import Document


# --- Klassen ---
class UploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ["title", "file", "mime"]