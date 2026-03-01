from rest_framework import serializers
from knowledge.models import Document

class UploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ["title", "file", "mime"]