# --- Import Django ---
from django import forms
# --- Import App-Content ---
from .models import KBEntry, Document, TempNotice, MaintenanceTemplate


# ---  Variablen ---
TAG_CHOICES = [
    ("onboarding", "Onboarding"),
    ("vertrag", "Vertrag"),
    ("kündigung", "Kündigung"),
    ("technik", "Technik"),
    ("abrechnung", "Abrechnung"),
    ("faq", "FAQ"),
    ("support", "Support"),
]

# --- Forms ---
class KBEntryForm(forms.ModelForm):
    tags = forms.MultipleChoiceField(
        choices=TAG_CHOICES,
        required=False,
        widget=forms.SelectMultiple(attrs={
            "class": "input",
            "size": 6,       # Anzahl sichtbarer Einträge
        })
    )

    class Meta:
        model = KBEntry
        fields = ["title", "body_md", "tags"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "input"}),
            "body_md": forms.Textarea(attrs={"class": "input", "rows": 8}),
        }

    def clean_tags(self):
        """Ensure tags are stored as list (JSONField)"""
        return self.cleaned_data["tags"]
    
class DocumentUploadForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ["file", "category"]
        widgets = {
            "file": forms.ClearableFileInput(attrs={"class": "input"}),
            "category": forms.Select(attrs={"class": "input"}),
        }

    def save(self, commit=True, user=None):
        doc = super().save(commit=False)
        # Titel automatisch aus Dateiname
        if not doc.title:
            doc.title = self.cleaned_data["file"].name
        doc.mime = self.cleaned_data["file"].content_type
        if user and not doc.created_by_id:
            doc.created_by = user
        if commit:
            doc.save()
        return doc

class TempNoticeForm(forms.ModelForm):
    class Meta:
        model = TempNotice
        fields = ["title", "body", "mode", "scope", "priority", "starts_at", "ends_at", "enabled"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "input"}),
            "body": forms.Textarea(attrs={"class": "input", "rows": 4}),
            "starts_at": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "input"}),
            "ends_at": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "input"}),
            "mode": forms.Select(attrs={"class": "input"}),
            "scope": forms.TextInput(attrs={"class": "input"}),
            "priority": forms.NumberInput(attrs={"class": "input"}),
        }

class MaintenanceTemplateForm(forms.ModelForm):
    class Meta:
        model = MaintenanceTemplate
        fields = ["title", "body", "severity", "default_mode", "default_scope"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "input"}),
            "body": forms.Textarea(attrs={"class": "input", "rows": 4}),
        }
