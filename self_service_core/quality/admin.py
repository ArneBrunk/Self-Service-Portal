from django.contrib import admin
from .models import EvalRun, EvalResult, EvalItem, HumanRating
# Register your models here.

@admin.register(EvalRun)
class EvalRunAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "created_by", "created_at", "status", "total", "evaluated", "accuracy_auto", "citation_compliance")
    list_filter = ("status", "created_at", "created_by")
    search_fields = ("name", "created_by__username")

@admin.register(EvalResult)
class EvalResultAdmin(admin.ModelAdmin):
    list_display = ("id", "run", "item", "status_ok", "sources_ok", "semantic_ok", "created_at")
    list_filter = ("status_ok", "sources_ok", "semantic_ok", "created_at")
    search_fields = ("item__question", "run__name")

@admin.register(EvalItem)
class EvalItemAdmin(admin.ModelAdmin):
    list_display = ("id", "question", "last_accuracy", "updated_at")
    search_fields = ("question",)   

    