# --- Import Django ---
from django.db import models
from django.conf import settings


# --- Models ---
class EvalRun(models.Model):
    STATUS_CHOICES = [
        ("running", "running"),
        ("done", "done"),
        ("failed", "failed"),
    ]

    SEMANTIC_METHOD_CHOICES = [
        ("v1", "V1 (Coverage)"),
        ("v2", "V2 (Hybrid: Coverage + Global)"),
        ("legacy", "Legacy (Global Cosine)"),
    ]

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)

    name = models.CharField(max_length=120, default="Iteration")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="running")

    # Iterationsparameter
    retrieval_top_k = models.IntegerField(default=6)
    semantic_threshold = models.FloatField(default=0.80)
    prompt_version = models.CharField(max_length=50, default="v1")

    semantic_method = models.CharField(
        max_length=20,
        choices=SEMANTIC_METHOD_CHOICES,
        default="v1",
    )
    rag_enabled = models.BooleanField(default=True)
    citations_required = models.BooleanField(default=True)
    dataset_name = models.CharField(max_length=120, blank=True, default="gematik")
    dataset_version = models.CharField(max_length=60, blank=True, default="v1")
    min_recall = models.FloatField(null=True, blank=True)
    min_f1 = models.FloatField(null=True, blank=True)
    min_global = models.FloatField(null=True, blank=True)
    total = models.IntegerField(default=0)
    evaluated = models.IntegerField(default=0)
    accuracy_auto = models.FloatField(null=True, blank=True)          
    citation_compliance = models.FloatField(null=True, blank=True)   
    error_message = models.TextField(blank=True, default="")


class EvalItem(models.Model):
    CATEGORY_CHOICES = [
        ("concept", "Begriffe/Rollen/Grundlagen"),
        ("architecture", "Architektur/Komponenten"),
        ("process", "Prozesse/Fachlogik"),
        ("support", "Fehler/Supportfall"),
        ("governance", "Governance/Transfer"),
    ]

    KB_EXPECTED_CHOICES = [
        ("yes", "Wissensbasis vorhanden"),
        ("partial", "teilweise vorhanden"),
        ("no", "Wissensbasis fehlt (Wissenslücke)"),
    ]

    question = models.TextField()
    expected_hint = models.TextField(blank=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default="concept")
    kb_expected = models.CharField(max_length=10, choices=KB_EXPECTED_CHOICES, default="yes")
    should_escalate = models.BooleanField(default=False)
    expected_sources_min = models.IntegerField(default=1)  
    tags = models.JSONField(blank=True, default=list) 
    last_accuracy = models.BooleanField(null=True)
    notes = models.TextField(blank=True)
    last_similarity = models.FloatField(null=True, blank=True)
    last_recall_like = models.FloatField(null=True, blank=True)
    last_precision_like = models.FloatField(null=True, blank=True)
    last_f1_like = models.FloatField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class EvalResult(models.Model):
    ESCALATION_REASON_CHOICES = [
        ("no_kb", "fehlende Wissensbasis"),
        ("low_confidence", "geringe Antwortsicherheit/Qualität"),
        ("policy", "Policy/Compliance"),
        ("missing_context", "fehlende Kontextinformationen"),
        ("system_error", "System-/Schnittstellenfehler"),
        ("other", "Sonstiges"),
    ]

    CLOSED_LOOP_STATUS_CHOICES = [
        ("none", "keine Wissenslücke erkannt"),
        ("detected", "Wissenslücke erkannt"),
        ("ticketed", "Ticket/Task angelegt"),
        ("kb_written", "KB-Artikel erstellt/erweitert"),
        ("reintegrated", "Retrieval aktualisiert (re-integriert)"),
    ]

    run = models.ForeignKey(EvalRun, on_delete=models.CASCADE, related_name="results")
    item = models.ForeignKey("EvalItem", on_delete=models.CASCADE)

    answer = models.TextField(blank=True, default="")
    sources = models.JSONField(blank=True, default=list)

    status_ok = models.BooleanField(default=False)
    sources_ok = models.BooleanField(default=False)
    has_citation_markers = models.BooleanField(default=False, null=True)

    semantic_ok = models.BooleanField(default=False)
    semantic_similarity = models.FloatField(null=True, blank=True)
    semantic_recall_like = models.FloatField(null=True, blank=True)
    semantic_precision_like = models.FloatField(null=True, blank=True)
    semantic_f1_like = models.FloatField(null=True, blank=True)

    auto_correct = models.BooleanField(default=False)

    escalated = models.BooleanField(default=False)
    escalation_reason = models.CharField(
        max_length=30,
        choices=ESCALATION_REASON_CHOICES,
        blank=True,
        default="",
    )
    handover_context = models.JSONField(blank=True, default=dict)
    handover_context_ok = models.BooleanField(null=True, blank=True)
    knowledge_gap = models.BooleanField(default=False)
    closed_loop_status = models.CharField(
        max_length=20,
        choices=CLOSED_LOOP_STATUS_CHOICES,
        default="none",
    )
    kb_article_ref = models.CharField(max_length=200, blank=True, default="") 
    transparency_score = models.IntegerField(null=True, blank=True) 
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("run", "item")


class HumanRating(models.Model):
    run = models.ForeignKey("EvalRun", on_delete=models.CASCADE, related_name="human_ratings")
    item = models.ForeignKey("EvalItem", on_delete=models.CASCADE, related_name="human_ratings")
    rater = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    correctness = models.IntegerField(null=True, blank=True)    
    completeness = models.IntegerField(null=True, blank=True)   
    citations = models.IntegerField(null=True, blank=True)      
    clarity = models.IntegerField(null=True, blank=True)       
    usefulness = models.IntegerField(null=True, blank=True)    
    comment = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("run", "item", "rater")
        indexes = [
            models.Index(fields=["run", "item"]),
            models.Index(fields=["run", "rater"]),
        ]
