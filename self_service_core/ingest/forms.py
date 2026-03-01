# --- Import Django ---
from django import forms

# --- Import App-Content ---
from knowledge.models import Document


# --- Forms ---
class DocumentUploadForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ["title", "file", "mime"]
