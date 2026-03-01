# --- Import Django ---
from django.db import models
from django.conf import settings
from django.utils import timezone


# ---  Variablen ---
STATUS = [
    ("draft", "Draft"),
    ("review", "Review"),
    ("published", "Published"),
    ("archived", "Archived"),
]

# --- Models ---
class Document(models.Model):
    STATUS_CHOICES = [
        ("uploaded", "Hochgeladen"),
        ("extracting", "Extrahiere"),
        ("indexing", "Indexiere"),
        ("indexed", "Fertig"),
        ("error", "Fehler"),
    ]
    CATEGORY_CHOICES = [
        ("manual", "Handbuch / Anleitung"),
        ("policy", "Richtlinie / Policy"),
        ("faq", "FAQ / Häufige Fragen"),
        ("other", "Sonstiges"),
    ]
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to="docs/")
    mime = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="uploaded")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    updated_at = models.DateTimeField(auto_now=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default="other")

    # NEU:
    index_progress = models.IntegerField(default=0)   # 0–100
    index_message = models.TextField(blank=True)
    indexed_chunks = models.IntegerField(default=0)


class KBEntry(models.Model):
    title = models.CharField(max_length=255)
    body_md = models.TextField()
    tags = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="draft")
    version = models.IntegerField(default=1)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    updated_at = models.DateTimeField(auto_now=True)

class TempNotice(models.Model):
    MODE = [("prepend","Prepend"),("append","Append"),("override","Override")]
    SEVERITY = [("info", "Hinweis"),("warning", "Warnung"), ("critical", "Störung"), ("maintenance", "Wartung")]
    severity = models.CharField(max_length=12, choices=SEVERITY, default="info", help_text="Bestimmt Farbe & Wichtigkeit im Chat (Info/Warning/Critical).",)
    title = models.CharField(max_length=200)
    body = models.TextField()
    mode = models.CharField(max_length=8, choices=MODE, default="prepend")
    scope = models.CharField(max_length=100, default="global")
    priority = models.IntegerField(default=50)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    enabled = models.BooleanField(default=True)

class MaintenanceTemplate(models.Model):
    """
    Vorlage für Wartungs-/Störungsmeldungen.
    """
    SEVERITY_CHOICES = [("info", "Hinweis"),("warning", "Warnung"), ("critical", "Störung"), ("maintenance", "Wartung")]
    title = models.CharField(max_length=200)
    body = models.TextField()
    severity = models.CharField(max_length=16, choices=SEVERITY_CHOICES, default="info")
    default_mode = models.CharField(max_length=8, choices=TempNotice.MODE, default="prepend")
    default_scope = models.CharField(max_length=100, default="global")

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_severity_display()}: {self.title}"


class Chunk(models.Model):
    SOURCE = [("doc","Document"),("kb","KBEntry"), ("pdf","PDF")]
    source_kind = models.CharField(max_length=8, choices=SOURCE)
    source_id = models.IntegerField()
    ord = models.IntegerField(default=0)
    text = models.TextField()
    meta = models.JSONField(default=dict, blank=True)
    class Meta:
        indexes = [models.Index(fields=["source_kind","source_id"]) ]



GAP_STATUS = [
    ("open", "Open"),
    ("in_progress", "In progress"),
    ("resolved", "Resolved"),
    ("ignored", "Ignored"),
]

GAP_REASON = [
    ("low_retrieval", "Low retrieval confidence"),
    ("non_answer", "Model non-answer"),
    ("keyword", "Keyword escalation"),
    ("citations_missing", "Citations missing"),
    ("other", "Other"),
]


class KnowledgeGap(models.Model):
    """
    Ein KnowledgeGap ist ein 'Cluster' ähnlicher, nicht (sicher) lösbarer Anfragen.
    embedding wird (wie bei Chunks) per Raw-SQL/pgvector geführt.
    """
    title = models.CharField(max_length=255, blank=True)
    representative_question = models.TextField()
    representative_question_norm = models.TextField(db_index=True)  # simple dedupe-key

    status = models.CharField(max_length=20, choices=GAP_STATUS, default="open")
    priority = models.IntegerField(default=50)

    count = models.IntegerField(default=1)
    reason_top = models.CharField(max_length=32, choices=GAP_REASON, default="other")

    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_gaps"
    )

    linked_kb_entry_id = models.IntegerField(null=True, blank=True)  # optional: später FK auf KBEntry

    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(default=timezone.now)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "-count"]),
            models.Index(fields=["-last_seen_at"]),
        ]

    def __str__(self):
        return f"[{self.status}] {self.title or self.representative_question[:60]}"


class KnowledgeGapEvent(models.Model):
    """
    Jeder einzelne Vorfall (eine konkrete Anfrage), die zu einem Gap führt.
    """
    gap = models.ForeignKey(KnowledgeGap, on_delete=models.CASCADE, related_name="events")

    question_raw = models.TextField()
    question_redacted = models.TextField()
    reason = models.CharField(max_length=32, choices=GAP_REASON, default="other")

    best_score = models.FloatField(null=True, blank=True)
    threshold = models.FloatField(null=True, blank=True)

    # kleine, nützliche Debug-/Kontextdaten:
    top_sources = models.JSONField(default=list, blank=True)  # [{title, source_kind, source_id, page, score}, ...]
    meta = models.JSONField(default=dict, blank=True)         # frei: z.B. {"semantic_method":"v2"}

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    session_id = models.IntegerField(null=True, blank=True)
    ticket_id = models.IntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["reason", "-created_at"]),
            models.Index(fields=["ticket_id"]),
            models.Index(fields=["session_id"]),
        ]

    def __str__(self):
        return f"{self.reason} @ {self.created_at:%Y-%m-%d %H:%M}"
