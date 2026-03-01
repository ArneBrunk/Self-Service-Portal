# --- Import Django ---
from django.views import View
from django.utils.timezone import now
from django.db.models import Count, Q
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models.functions import TruncDay
from django.views import View
from django.http import JsonResponse
from django.utils import timezone
from rest_framework.test import APIRequestFactory
from django.db import close_old_connections
from django.db.models import Count, Avg
from django.db import connection

# --- Import App-Content ---
from .models import CompanyProfile, ChatbotConfig
from .forms import CompanyProfileForm, ChatbotConfigForm, StaffProfileForm
from .mixin import StaffRequiredMixin, StaffAdminRequiredMixin
#--------------
from quality.models import EvalItem, EvalRun, EvalResult, HumanRating
from quality.eval_utils import is_semantically_correct_v2, has_valid_citation_markers, normalize_sources, filter_defaults_for_model, extract_cited_indices, semantic_global_similarity_ok, is_semantically_correct_v1
from quality.forms import EvalItemForm
#--------------
from chat.views import ChatView
from chat.models import ChatSession
#--------------
from knowledge.models import KBEntry, Document, TempNotice, MaintenanceTemplate, KnowledgeGap, KnowledgeGapEvent
from knowledge.forms import KBEntryForm, DocumentUploadForm, TempNoticeForm, MaintenanceTemplateForm
from knowledge.index_pipeline import start_pipeline_async
from knowledge.ingestion import index_kb_entry
#--------------
from users.models import Customer
#--------------
from tickets.models import TicketSystemConfig, Ticket
from tickets.forms import TicketSystemConfigForm
from tickets.services import export_ticket_to_external, close_ticket_in_external


# --- Import App-Content ---
from typing import Optional
import threading
from datetime import timedelta

# ---  Helper-Funktionen ---
def reindex_kb_entry(entry):
    with connection.cursor() as cur:
        cur.execute(
            "DELETE FROM knowledge_chunk WHERE source_kind = %s AND source_id = %s",
            ["kb", entry.id],
        )
    index_kb_entry(entry)


# --- Views ---
class StaffProfileView(StaffRequiredMixin, View):
    template_name = "staff/profile.html"

    def get(self, request):
        form = StaffProfileForm(instance=request.user)
        return render(request, self.template_name, {
            "form": form,
            "role": request.user.staff.role,})
    
    def post(self, request):
        user = request.user
        form = StaffProfileForm(request.POST, instance=user)

        if form.is_valid():
            form.save()
            messages.success(request, "Dein Profil wurde aktualisiert.")
            return redirect("staff-profile")

        context = {
            "form": form,
            "role": request.user.staff.role,
        }
        return render(request, self.template_name, context)
class StaffDashboardView(StaffRequiredMixin, View):
    template_name = "staff/dashboard.html"

    def get(self, request):
        today = now().date()
        seven_days_ago = today - timedelta(days=6)
        thirty_days_ago = today - timedelta(days=29)

        # --- Grund-Kennzahlen ---
        total_tickets = Ticket.objects.count()
        total_customers = Customer.objects.count()
        total_chats = ChatSession.objects.count()

        tickets_by_status_qs = (
            Ticket.objects.values("status")
            .annotate(count=Count("id"))
        )
        tickets_by_status = {row["status"]: row["count"] for row in tickets_by_status_qs}

        chats_today = ChatSession.objects.filter(
            created_at__date=today
        ).count()

        chats_last_7_days = ChatSession.objects.filter(
            created_at__date__gte=seven_days_ago
        ).count()

        chats_last_30_days = ChatSession.objects.filter(
            created_at__date__gte=thirty_days_ago
        ).count()

        # --- Chats pro Tag (letzte 7 Tage) ---
        chats_per_day_qs = (
            ChatSession.objects.filter(created_at__date__gte=seven_days_ago)
            .annotate(day=TruncDay("created_at"))
            .values("day")
            .annotate(count=Count("id"))
            .order_by("day")
        )
        day_labels = []
        day_data = []
        day_map = {row["day"].date(): row["count"] for row in chats_per_day_qs}

        for i in range(7):
            d = seven_days_ago + timedelta(days=i)
            day_labels.append(d.strftime("%d.%m."))
            day_data.append(day_map.get(d, 0))

        # --- Quality Score (letzte 30 Tage) ---
        escalated_last_30 = Ticket.objects.filter(
            created_at__date__gte=thirty_days_ago,
            status="escalated",
        ).count()

        if chats_last_30_days > 0:
            quality_score = max(
                0,
                min(
                    100,
                    round(100 * (1 - (escalated_last_30 / chats_last_30_days)), 1),
                ),
            )
        else:
            quality_score = None 
        rated_qs = ChatSession.objects.exclude(rating__isnull=True)

        rating_avg = rated_qs.aggregate(v=Avg("rating"))["v"] or 0
        rating_count = rated_qs.count()
        rating_rate = (rating_count / total_chats * 100) if total_chats else 0
        latest_ratings = rated_qs.select_related("user").order_by("-rated_at")[:10]

        rating_dist = {i: 0 for i in range(1, 6)}
        for row in rated_qs.values("rating").annotate(c=Count("id")):
            rating_dist[row["rating"]] = row["c"]

        context = {
            "total_tickets": total_tickets,
            "total_customers": total_customers,
            "total_chats": total_chats,
            "tickets_by_status": tickets_by_status,
            "chats_today": chats_today,
            "chats_last_7_days": chats_last_7_days,
            "chats_last_30_days": chats_last_30_days,
            "chart_day_labels": day_labels,
            "chart_day_data": day_data,
            "quality_score": quality_score,
            "escalated_last_30": escalated_last_30,
            "active_tab": "dashboard",
             "rating_avg": round(rating_avg, 2),
            "rating_count": rating_count,
            "rating_rate": round(rating_rate, 1),
            "latest_ratings": latest_ratings,
            "rating_dist": rating_dist,
        }
        
        return render(request, self.template_name, context)
class StaffTicketsView(StaffRequiredMixin, View):
    template_name = "staff/tickets.html"

    def get(self, request):
            # URL-Filter: ?status=escalated etc.
            status_filter = request.GET.get("status", "escalated")

            # Basis-Query
            qs = Ticket.objects.all().order_by("-created_at")

            # Filter anwenden
            if status_filter == "escalated":
                qs = qs.filter(status="escalated")
            elif status_filter == "in_progress":
                qs = qs.filter(status="in_progress")
            elif status_filter == "solved":
                qs = qs.filter(status="solved")
            # anderen Status ignorieren

            # Counts für Tabs
            counts = {
                "all": Ticket.objects.count(),
                "escalated": Ticket.objects.filter(status="escalated").count(),
                "in_progress": Ticket.objects.filter(status="in_progress").count(),
                "solved": Ticket.objects.filter(status="solved").count(),
            }

            return render(
                request,
                self.template_name,
                {
                    "tickets": qs,
                    "counts": counts,
                    "status_filter": status_filter,
                    "active_tab": "tickets",  # für Header-Highlighting
                },
            )
    def post(self, request):
        """
        Wird aufgerufen, wenn im Ticket-Listing ein Button geklickt wird,
        z.B. 'Exportieren'.
        """
        action = request.POST.get("action")
        ticket_id = request.POST.get("ticket_id")

        if action == "export" and ticket_id:
            ticket = get_object_or_404(Ticket, pk=ticket_id)

            success, msg = export_ticket_to_external(ticket)
            if success:
                messages.success(request, f"Ticket #{ticket.id} exportiert.")
            else:
                messages.error(request, f"Ticket #{ticket.id} konnte nicht exportiert werden: {msg}")

        elif action == "close_external":
            ticket = get_object_or_404(Ticket, pk=ticket_id)
            success, msg = close_ticket_in_external(ticket)
            if success:
                messages.success(request, f"Ticket #{ticket.id} geschlossen.")
            else:
                messages.error(request, f"Ticket #{ticket.id} konnte nicht geschlossen werden: {msg}")

        # Zurück zur aktuellen Filteransicht
        status_filter = request.GET.get("status", "all")
        return redirect(f"{request.path}?status={status_filter}")
class StaffSettingsView(StaffAdminRequiredMixin, View):
    template_name = "staff/settings.html"

    def get(self, request):
        ticket_cfg = TicketSystemConfig.get_solo()
        ticket_form = TicketSystemConfigForm(instance=ticket_cfg)
        company = CompanyProfile.get_solo()
        bot = ChatbotConfig.get_solo()
        company_form = CompanyProfileForm(instance=company)
        bot_form = ChatbotConfigForm(instance=bot)
        return render(
            request,
            self.template_name,
            {
                "company_form": company_form,
                "bot_form": bot_form,
                "active_tab": "settings", 
                "ticket_form": ticket_form,
            },
        )

    def post(self, request):
        company = CompanyProfile.get_solo()
        bot = ChatbotConfig.get_solo()
        ticket_cfg = TicketSystemConfig.get_solo()
        company_form = CompanyProfileForm(instance=company)
        bot_form = ChatbotConfigForm(instance=bot)
        ticket_form = TicketSystemConfigForm(instance=ticket_cfg)

        if "save_company" in request.POST:
            company_form = CompanyProfileForm(request.POST, request.FILES, instance=company)
            bot_form = ChatbotConfigForm(instance=bot)
            ticket_form = TicketSystemConfigForm(instance=ticket_cfg)

            if company_form.is_valid():
                obj = company_form.save(commit=False)
                obj.updated_by = request.user
                obj.save()
                messages.success(request, "Company settings saved.")
                return redirect("staff-settings")

        elif "save_bot" in request.POST:
            company_form = CompanyProfileForm(instance=company)
            bot_form = ChatbotConfigForm(request.POST, instance=bot)
            ticket_form = TicketSystemConfigForm(instance=ticket_cfg)

            if bot_form.is_valid():
                obj = bot_form.save(commit=False)
                obj.updated_by = request.user
                obj.save()
                messages.success(request, "Chatbot settings saved.")
                return redirect("staff-settings")

        elif "save_ticket_system" in request.POST:
            company_form = CompanyProfileForm(instance=company)
            bot_form = ChatbotConfigForm(instance=bot)
            ticket_form = TicketSystemConfigForm(request.POST, instance=ticket_cfg)

            if ticket_form.is_valid():
                ticket_form.save()
                messages.success(request, "Ticket system settings saved.")
                return redirect("staff-settings")

        else:
            company_form = CompanyProfileForm(instance=company)
            bot_form = ChatbotConfigForm(instance=bot)
            ticket_form = TicketSystemConfigForm(instance=ticket_cfg)

        return render(request, self.template_name, {
            "company_form": company_form,
            "bot_form": bot_form,
            "ticket_form": ticket_form,
            "active_tab": "settings",
        })


SEMANTIC_METHOD_CHOICES = {
    "v1": "V1 (Coverage)",
    "v2": "V2 (Hybrid: Coverage + Global)",
    "legacy": "Legacy (Global Cosine)",
}

class StaffQualityView(StaffRequiredMixin, View):
    template_name = "staff/quality.html"

    def get(self, request):
        # 1) Runs für Auswahl (Dropdown)
        runs_for_select = EvalRun.objects.filter(status="done").order_by("-created_at")[:200]
        # 2) Chart-Runs getrennt nach RAG off / on (je 50, chronologisch)
        runs_rag_off = list(
            EvalRun.objects.filter(status="done", rag_enabled=False).order_by("-created_at")[:50]
        )
        runs_rag_on = list(
            EvalRun.objects.filter(status="done", rag_enabled=True).order_by("-created_at")[:50]
        )
        runs_rag_off.reverse()
        runs_rag_on.reverse()

        def human_score_map(run_ids):
            """
            Map run_id -> human_avg (0..2) über correctness/completeness/citations.
            NULL-Werte werden ignoriert (Avg ignoriert NULL).
            """
            if not run_ids:
                return {}

            rows = (
                HumanRating.objects
                .filter(run_id__in=run_ids)
                .values("run_id")
                .annotate(
                    c_avg=Avg("correctness"),
                    comp_avg=Avg("completeness"),
                    cit_avg=Avg("citations"),
                )
            )

            m = {}
            for r in rows:
                vals = [r["c_avg"], r["comp_avg"], r["cit_avg"]]
                vals = [float(v) for v in vals if v is not None]
                m[r["run_id"]] = (sum(vals) / len(vals)) if vals else None  
            return m

        off_ids = [r.id for r in runs_rag_off]
        on_ids  = [r.id for r in runs_rag_on]

        human_off = human_score_map(off_ids)
        human_on  = human_score_map(on_ids)

        def build_series(runs, human_map):
            labels = [r.created_at.strftime("%d.%m %H:%M") for r in runs]
            acc = [round((r.accuracy_auto or 0) * 100, 1) for r in runs]
            cit = [
                round((r.citation_compliance or 0) * 100, 1) if r.citation_compliance is not None else None
                for r in runs
            ]
            hum = [
                round(human_map.get(r.id), 2) if human_map.get(r.id) is not None else None
                for r in runs
            ]  # 0..2
            return labels, acc, cit, hum

        chart_labels_rag_off, chart_accuracy_rag_off, chart_citation_rag_off, chart_human_rag_off = build_series(runs_rag_off, human_off)
        chart_labels_rag_on,  chart_accuracy_rag_on,  chart_citation_rag_on,  chart_human_rag_on  = build_series(runs_rag_on,  human_on)


        # 3) Selected Run run=id oder newest

        run_id = request.GET.get("run")
        if run_id:
            selected_run = EvalRun.objects.filter(id=run_id, status="done").first()
        else:
            selected_run = runs_for_select.first()
        # 4) Item-Übersicht (global über alle Runs)
        items = (
            EvalItem.objects.all()
            .annotate(
                run_count=Count("evalresult", distinct=True),
                correct_count=Count("evalresult", filter=Q(evalresult__auto_correct=True), distinct=True),
            )
            .order_by("-run_count", "id")
        )
        total_items = items.count()
        # 5) Run-Detail: Ergebnisse + run-basierte KPIs
        run_results = []
        run_kpis = {
            "n_items": 0,
            "status_ok_rate": 0.0,
            "sources_ok_rate": 0.0,
            "semantic_ok_rate": 0.0,
            "auto_accuracy": 0.0,
            "citation_compliance": None,
            "escalation_rate": 0.0,
            "knowledge_gap_rate": 0.0,
        }

        if selected_run:
            run_results = (
                EvalResult.objects
                .filter(run=selected_run)
                .select_related("item")
                .order_by("item_id")
            )

            n_items = run_results.count()

            if n_items:
                status_ok_rate = run_results.filter(status_ok=True).count() / n_items
                sources_ok_rate = run_results.filter(sources_ok=True).count() / n_items
                semantic_ok_rate = run_results.filter(semantic_ok=True).count() / n_items
                auto_accuracy = run_results.filter(auto_correct=True).count() / n_items
                escalation_rate = run_results.filter(escalated=True).count() / n_items
                knowledge_gap_rate = run_results.filter(knowledge_gap=True).count() / n_items

                if selected_run.rag_enabled and selected_run.citations_required:
                    citation_compliance = (
                        run_results
                        .filter(sources_ok=True, has_citation_markers=True)
                        .count() / n_items
                    )
                else:
                    citation_compliance = None

                run_kpis = {
                    "n_items": n_items,
                    "status_ok_rate": round(status_ok_rate * 100, 1),
                    "sources_ok_rate": round(sources_ok_rate * 100, 1),
                    "semantic_ok_rate": round(semantic_ok_rate * 100, 1),
                    "auto_accuracy": round(auto_accuracy * 100, 1),
                    "escalation_rate": round(escalation_rate * 100, 1),
                    "knowledge_gap_rate": round(knowledge_gap_rate * 100, 1),
                    "citation_compliance": round(citation_compliance * 100, 1)
                        if citation_compliance is not None else None,
                }

        # 6) UI Defaults aus selected_run übernehmen
        ui_threshold = float(getattr(selected_run, "semantic_threshold", 0.80) or 0.80) if selected_run else 0.80
        ui_sem_method = getattr(selected_run, "semantic_method", "v1") if selected_run else "v1"

        # 7) Ratings pro Item (aktueller User, selected_run)
        my_ratings = {}
        if selected_run:
            qs = HumanRating.objects.filter(run=selected_run, rater=request.user).order_by("-created_at")
            for hr in qs:
                my_ratings.setdefault(hr.item_id, hr)


        # 8) Context final
        context = {
            "active_tab": "quality",

            "items": items,
            "total_items": total_items,

            "runs": runs_for_select,
            "selected_run": selected_run,
            "run_results": run_results,
            "run_kpis": run_kpis,

            "threshold": ui_threshold,
            "semantic_method": ui_sem_method,
            "semantic_method_choices": SEMANTIC_METHOD_CHOICES,

            "chart_labels_rag_off": chart_labels_rag_off,
            "chart_accuracy_rag_off": chart_accuracy_rag_off,
            "chart_citation_rag_off": chart_citation_rag_off,
            "chart_human_rag_off": chart_human_rag_off,

            "chart_labels_rag_on": chart_labels_rag_on,
            "chart_accuracy_rag_on": chart_accuracy_rag_on,
            "chart_citation_rag_on": chart_citation_rag_on,
            "chart_human_rag_on": chart_human_rag_on,

            "my_ratings": my_ratings,
        }
        return render(request, self.template_name, context)


    def post(self, request):
        """
        Startet einen Quality-Run in einem Thread.
        Bei AJAX IMMER JSON: {"run_id": ...} oder {"error": ...}
        """
        try:

            # 1) Parameter 
            limit = int(request.POST.get("limit", 30))
            limit = max(1, min(limit, 60))
            threshold = float(request.POST.get("threshold", 0.70))
            threshold = max(0.0, min(threshold, 0.99))
            top_k = int(request.POST.get("top_k", 6))
            top_k = max(1, min(top_k, 20))
            prompt_version = request.POST.get("prompt_version", "v1")
            semantic_method = request.POST.get("semantic_method", "v1")
            if semantic_method not in dict(SEMANTIC_METHOD_CHOICES):
                semantic_method = "v1"

            min_f1_offset = float(request.POST.get("min_f1_offset", 0.03))
            min_global_offset = float(request.POST.get("min_global_offset", -0.02))

            rag_enabled = request.POST.get("rag_enabled", "1") == "1"
            citations_required = request.POST.get("citations_required", "1") == "1"
            if not rag_enabled:
                citations_required = False

            # Schwellen abgeleitet 
            min_recall = threshold
            min_f1 = max(0.0, threshold - min_f1_offset)
            min_global = max(0.0, min(0.99, threshold + min_global_offset))


            # 2) Run anlegen
            run = EvalRun.objects.create(
                created_by=request.user,
                name=f"Run {now().strftime('%Y-%m-%d %H:%M:%S')}",
                status="running",
                retrieval_top_k=top_k,
                semantic_threshold=threshold,
                prompt_version=prompt_version,
                semantic_method=semantic_method,
                rag_enabled=rag_enabled,
                citations_required=citations_required,
                min_recall=min_recall,
                min_f1=min_f1,
                min_global=min_global,
                total=0,
                evaluated=0,
            )
            # 3) Background-Worker
            def worker(
                run_id: int,
                user_id: int,
                limit_: int,
                thr_: float,
                top_k_: int,
                pv_: str,
                sem_method_: str,
                min_recall_: float,
                min_f1_: float,
                min_global_: float,
                rag_enabled_: bool,
                citations_required_: bool,
            ):
                close_old_connections()
                from django.contrib.auth import get_user_model
                User = get_user_model()
                user = User.objects.get(id=user_id)
                run_obj = EvalRun.objects.get(id=run_id)
                factory = APIRequestFactory()
                items_ = list(EvalItem.objects.order_by("id")[:limit_])

                run_obj.total = len(items_)
                run_obj.evaluated = 0
                run_obj.status = "running"
                run_obj.save(update_fields=["total", "evaluated", "status"])

                correct_ = 0
                citation_ok_ = 0

                def map_escalation_reason(reason: Optional[str], rag_on: bool) -> str:
                    if not reason:
                        return ""
                    r = str(reason)

                    # ChatView compute_escalation: keyword | non_answer | low_retrieval
                    if r == "low_retrieval":
                        # Wenn RAG aus ist, ist das NICHT "no_kb", sondern fehlender Kontext
                        return "no_kb" if rag_on else "missing_context"
                    if r == "non_answer":
                        return "missing_context"
                    if r == "keyword":
                        return "policy"

                    if r in {"no_kb", "low_confidence", "policy", "missing_context", "system_error", "other"}:
                        return r
                    return "other"

                for idx, it in enumerate(items_, start=1):
                    api_req = factory.post(
                        "/api/chat",
                        {
                            "message": it.question,
                            "top_k": top_k_,
                            "prompt_version": pv_,
                            "rag_enabled": rag_enabled_,
                            "citations_required": citations_required_,
                        },
                        format="json",
                    )
                    api_req.user = user

                    resp = ChatView.as_view()(api_req)
                    data = getattr(resp, "data", {}) or {}

                    answer = (data.get("answer", "") or "").strip()
                    raw_sources = data.get("sources", []) or []
                    status_ok = 200 <= getattr(resp, "status_code", 500) < 300

                    escalated = bool(data.get("escalated") or False)
                    escalation_reason = map_escalation_reason(data.get("escalation_reason", None), rag_enabled_)
                    ticket_id = data.get("ticket_id", None)

                    kb_article_ref = data.get("kb_article_ref") or ""

                    # --- Quellen normalisieren ---
                    if raw_sources and isinstance(raw_sources[0], dict) and ("title" in raw_sources[0] or "snippet" in raw_sources[0]):
                        sources_all = raw_sources
                    else:
                        sources_all = normalize_sources(raw_sources)

                    sources_ok = len(sources_all) > 0
                    citation_checks_on = bool(rag_enabled_ and citations_required_)

                    # --- Marker-Validierung (nie Marker zulassen, wenn keine Quellen existieren) ---
                    if citation_checks_on:
                        if not sources_ok:
                            has_markers = False
                        else:
                            has_markers = has_valid_citation_markers(answer, len(sources_all))
                    else:
                        has_markers = None

                    # Nur tatsächlich zitierte Quellen speichern (wenn Marker valide)
                    cited_idx = extract_cited_indices(answer)
                    if (has_markers is True) and cited_idx:
                        sources = [s for s_i, s in enumerate(sources_all, start=1) if s_i in cited_idx]
                    else:
                        sources = sources_all

                    # --- Semantik ---
                    expected = getattr(it, "expected_hint", None)
                    semantic_ok = True
                    recall_like = precision_like = f1_like = 0.0
                    similarity = None

                    if expected:
                        if sem_method_ == "v2":
                            semantic_ok, scores = is_semantically_correct_v2(
                                answer,
                                expected,
                                min_recall=min_recall_,
                                min_f1=min_f1_,
                                min_global=min_global_,
                            )
                            recall_like = float(scores.get("recall_like", 0.0))
                            precision_like = float(scores.get("precision_like", 0.0))
                            f1_like = float(scores.get("f1_like", 0.0))
                            similarity = float(f1_like)

                        elif sem_method_ == "legacy":
                            semantic_ok, global_sim = semantic_global_similarity_ok(answer, expected, threshold=thr_)
                            similarity = float(global_sim)

                        else:  # v1
                            semantic_ok, scores = is_semantically_correct_v1(
                                answer,
                                expected,
                                min_recall=min_recall_,
                                min_f1=min_f1_,
                            )
                            recall_like = float(scores.get("recall_like", 0.0))
                            precision_like = float(scores.get("precision_like", 0.0))
                            f1_like = float(scores.get("f1_like", 0.0))
                            similarity = float(f1_like)

                    # --- auto_correct ---
                    if citation_checks_on:
                        matched = status_ok and sources_ok and (has_markers is True) and semantic_ok
                    else:
                        matched = status_ok and semantic_ok

                    # --- Closed Loop / Knowledge Gap ---
                    knowledge_gap = False
                    closed_loop_status = "none"

                    if escalated:
                        knowledge_gap = True
                        closed_loop_status = "ticketed" if ticket_id else "detected"
                    elif citation_checks_on and (not sources_ok or has_markers is False):
                        knowledge_gap = True
                        closed_loop_status = "detected"

                    # --- Handover Context ---
                    handover_context = {}
                    handover_context_ok = None

                    if escalated:
                        best_score = max((float(s.get("score", 0.0) or 0.0) for s in sources_all), default=0.0)
                        handover_context = {
                            "question": it.question,
                            "run_id": run_obj.id,
                            "item_id": it.id,
                            "reason": escalation_reason,
                            "best_score": round(best_score, 3),
                            "sources_count": len(sources_all),
                            "ticket_id": ticket_id,
                        }
                        # wenn RAG an: Kontext ok nur wenn Quellen da
                        handover_context_ok = bool(it.question) and (len(sources_all) > 0 if rag_enabled_ else True)

                    # --- Transparency Score (1..5) ---
                    if citation_checks_on:
                        raw = (
                            (1.0 if sources_ok else 0.0) * 0.4 +
                            (1.0 if (has_markers is True) else 0.0) * 0.4 +
                            (1.0 if semantic_ok else 0.0) * 0.2
                        )
                    else:
                        raw = 1.0 if semantic_ok else 0.5

                    transparency_score = max(1, min(5, int(round(raw * 4 + 1))))

                    defaults = {
                        "answer": answer,
                        "sources": sources,

                        "status_ok": status_ok,
                        "sources_ok": sources_ok,
                        "has_citation_markers": has_markers,

                        "semantic_ok": semantic_ok,
                        "semantic_similarity": similarity,
                        "semantic_recall_like": recall_like if expected and sem_method_ != "legacy" else None,
                        "semantic_precision_like": precision_like if expected and sem_method_ != "legacy" else None,
                        "semantic_f1_like": f1_like if expected and sem_method_ != "legacy" else None,

                        "auto_correct": matched,

                        "escalated": escalated,
                        "escalation_reason": escalation_reason,

                        "handover_context": handover_context,
                        "handover_context_ok": handover_context_ok,

                        "knowledge_gap": knowledge_gap,
                        "closed_loop_status": closed_loop_status,
                        "kb_article_ref": kb_article_ref,

                        "transparency_score": transparency_score,
                    }

                    # DB-write
                    EvalResult.objects.update_or_create(
                        run=run_obj,
                        item=it,
                        defaults=filter_defaults_for_model(EvalResult, defaults),
                    )

                    if matched:
                        correct_ += 1
                    if citation_checks_on and sources_ok and (has_markers is True):
                        citation_ok_ += 1

                    run_obj.evaluated = idx
                    # nicht bei jedem Item alle Felder schreiben (DB schonen)
                    if idx % 5 == 0 or idx == len(items_):
                        run_obj.save(update_fields=["evaluated"])

                # Run KPIs
                run_obj.accuracy_auto = (correct_ / run_obj.total) if run_obj.total else 0.0
                if citation_checks_on:
                    run_obj.citation_compliance = (citation_ok_ / run_obj.total) if run_obj.total else 0.0
                else:
                    run_obj.citation_compliance = None

                run_obj.status = "done"
                run_obj.save(update_fields=["accuracy_auto", "citation_compliance", "status"])

            t = threading.Thread(
                target=worker,
                args=(
                    run.id,
                    request.user.id,
                    limit,
                    threshold,
                    top_k,
                    prompt_version,
                    semantic_method,
                    min_recall,
                    min_f1,
                    min_global,
                    rag_enabled,
                    citations_required,
                ),
                daemon=True,
            )
            t.start()

            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"run_id": run.id})

            return redirect("staff-quality")

        except Exception as e:
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"error": str(e)}, status=500)
            raise
class StaffQualityQuestionsView(StaffRequiredMixin, View):
    template_name = "staff/quality_questions.html"

    def get(self, request):
        items = (
            EvalItem.objects.all()
            .annotate(
                run_count=Count("evalresult", distinct=True),
                correct_count=Count("evalresult", filter=Q(evalresult__auto_correct=True), distinct=True),
            )
            .distinct()
            .order_by("-run_count", "id")
        )

        form = EvalItemForm()
        return render(request, self.template_name, {
            "items": items,
            "form": form,
            "active_tab": "quality",
        })

    def post(self, request):
        form = EvalItemForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Testfrage wurde hinzugefügt.")
            return redirect("staff-quality-questions")

        # Wenn invalid: Liste trotzdem anzeigen
        items = (
            EvalItem.objects.all()
            .annotate(
                run_count=Count("results", distinct=True),
                correct_count=Count("results", filter=Q(results__auto_correct=True), distinct=True),
            )
            .order_by("-run_count", "id")
        )
        return render(request, self.template_name, {
            "items": items,
            "form": form,
            "active_tab": "quality",
        })
class StaffKnowledgeView(StaffRequiredMixin, View):
    template_name = "staff/knowledge.html"

    def get(self, request):
        status_filter = request.GET.get("status", "all")

        qs = KBEntry.objects.all().order_by("-updated_at")
        if status_filter == "draft":
            qs = qs.filter(status="draft")
        elif status_filter == "review":
            qs = qs.filter(status="review")
        elif status_filter == "published":
            qs = qs.filter(status="published")

        form = KBEntryForm()
        context = {
            "kb_entries": qs,
            "status_filter": status_filter,
            "form": form,
            "active_tab": "kb",
        }
        return render(request, self.template_name, context)

    def post(self, request):
        user = request.user
        form = KBEntryForm(request.POST)

        if form.is_valid():
            entry = form.save(commit=False)
            entry.created_by = user
            old_status = None
            if entry.pk:
                try:
                    old_status = KBEntry.objects.only("status").get(pk=entry.pk).status
                except KBEntry.DoesNotExist:
                    old_status = None

            staff_profile = getattr(user, "staff", None)
            if staff_profile and staff_profile.role == "admin":
                if "publish" in request.POST:
                    entry.status = "published"
                elif "review" in request.POST:
                    entry.status = "review"
                else:
                    entry.status = "draft"
            else:
                entry.status = "draft"

            entry.save()

            published_transition = (old_status != "published" and entry.status == "published")

            if published_transition:
                # 1) Gap(s) schließen
                KnowledgeGap.objects.filter(linked_kb_entry_id=entry.id).exclude(status="resolved").update(status="resolved")

                # 2) Reindex (delete + index)
                reindex_kb_entry(entry)

            messages.success(request, "Knowledge-Base Eintrag wurde gespeichert.")
            return redirect("staff-kb")

        # bei Fehler
        qs = KBEntry.objects.all().order_by("-updated_at")
        context = {
            "kb_entries": qs,
            "status_filter": "all",
            "form": form,
            "active_tab": "kb",
        }
        return render(request, self.template_name, context)
class StaffPdfUploadView(StaffRequiredMixin, View):
    template_name = "staff/pdf_upload.html"

    def get(self, request):
        category_filter = request.GET.get("category", "all")
        docs = Document.objects.all().order_by("-updated_at")
        if category_filter != "all":
            docs = docs.filter(category=category_filter)

        upload_form = DocumentUploadForm()
        context = {
            "documents": docs,
            "upload_form": upload_form,
            "category_filter": category_filter,
            "categories": Document.CATEGORY_CHOICES,
            "active_tab": "pdf",
        }
        return render(request, self.template_name, context)

    def post(self, request):
        upload_form = DocumentUploadForm(request.POST, request.FILES)

        if upload_form.is_valid():
            doc = upload_form.save(user=request.user)

            # Pipeline starten
            doc.status = "uploaded"
            doc.index_progress = 0
            doc.index_message = "Warte auf Verarbeitung…"
            doc.save(update_fields=["status", "index_progress", "index_message"])

            start_pipeline_async(doc.id)

            messages.success(request, f"Dokument '{doc.title}' wird verarbeitet.")
            return redirect("staff-pdf-upload")


        docs = Document.objects.all().order_by("-updated_at")
        context = {
            "documents": docs,
            "upload_form": upload_form,
            "category_filter": "all",
            "categories": Document.CATEGORY_CHOICES,
            "active_tab": "pdf",
        }
        return render(request, self.template_name, context)
class StaffPdfStatusView(StaffRequiredMixin, View):
    """
    Liefert den aktuellen Index-Status aller Dokumente als JSON.
    Wird vom Frontend per AJAX gepollt.
    """
    def get(self, request):
        docs = Document.objects.all().order_by("-updated_at").values(
            "id",
            "status",
            "index_progress",
            "index_message",
            "indexed_chunks",
            "category",
        )
        return JsonResponse({"documents": list(docs)})
class StaffPdfReindexView(StaffRequiredMixin, View):
    def post(self, request, pk):
        doc = get_object_or_404(Document, pk=pk)

        doc.status = "uploaded"
        doc.index_progress = 0
        doc.index_message = "Neuindexierung gestartet…"
        doc.save(update_fields=["status", "index_progress", "index_message"])

        start_pipeline_async(doc.id)

        messages.success(request, f"Dokument '{doc.title}' wird neu indexiert.")
        return redirect("staff-pdf-upload")
class StaffMaintenanceView(StaffRequiredMixin, View):
    template_name = "staff/maintenance.html"

    def get(self, request):
        notices = TempNotice.objects.all().order_by("-priority", "-starts_at")
        templates = MaintenanceTemplate.objects.all().order_by("-created_at")

        notice_form = TempNoticeForm()
        template_form = MaintenanceTemplateForm()

        context = {
            "notices": notices,
            "templates": templates,
            "notice_form": notice_form,
            "template_form": template_form,
            "active_tab": "maintenance",
        }
        return render(request, self.template_name, context)

    def post(self, request):
        user = request.user
        staff_profile = getattr(user, "staff", None)
        is_admin = bool(staff_profile and staff_profile.role == "admin")

        action = request.POST.get("action")

        # 1) Neue Störung aus Formular
        if action == "create_notice":
            form = TempNoticeForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, "Störungs-/Wartungsmeldung wurde erstellt.")
                return redirect("staff-maintenance")

        # 2) Störung aktivieren/deaktivieren
        if action in {"enable_notice", "disable_notice"}:
            notice = get_object_or_404(TempNotice, pk=request.POST.get("notice_id"))
            notice.enabled = (action == "enable_notice")
            notice.save(update_fields=["enabled"])
            messages.success(request, f"Meldung '{notice.title}' wurde {'aktiviert' if notice.enabled else 'deaktiviert'}.")
            return redirect("staff-maintenance")

        # 3) Störung löschen (nur Admin)
        if action == "delete_notice" and is_admin:
            notice = get_object_or_404(TempNotice, pk=request.POST.get("notice_id"))
            notice.delete()
            messages.success(request, "Meldung wurde gelöscht.")
            return redirect("staff-maintenance")

        # 4) Maintenance-Template anlegen
        if action == "create_template":
            t_form = MaintenanceTemplateForm(request.POST)
            if t_form.is_valid():
                t_form.save()
                messages.success(request, "Maintenance-Vorlage wurde erstellt.")
                return redirect("staff-maintenance")

        # 5) Template in konkrete Störungsmeldung umwandeln
        if action == "spawn_from_template":
            tmpl = get_object_or_404(MaintenanceTemplate, pk=request.POST.get("template_id"))
            # Default: sofort aktiv für 2 Stunden
            starts = now()
            ends = now() + timedelta(hours=2)
            TempNotice.objects.create(
                title=tmpl.title,
                body=tmpl.body,
                mode=tmpl.default_mode,
                scope=tmpl.default_scope,
                priority=50 if tmpl.severity == "info" else 80 if tmpl.severity == "warning" else 100,
                starts_at=starts,
                ends_at=ends,
                enabled=True,
            )
            messages.success(request, f"Störungsmeldung aus Vorlage '{tmpl.title}' erstellt.")
            return redirect("staff-maintenance")

        # Fallback: zurück
        messages.error(request, "Unbekannte Aktion oder ungültige Daten.")
        return redirect("staff-maintenance")
class StaffGapListView(StaffRequiredMixin, View):
    template_name = "staff/gaps_list.html"

    def get(self, request):
        status = request.GET.get("status", "open")
        q = (request.GET.get("q") or "").strip()

        gaps = KnowledgeGap.objects.all()
        if status:
            gaps = gaps.filter(status=status)

        if q:
            gaps = gaps.filter(representative_question__icontains=q)

        gaps = gaps.order_by("-count", "-last_seen_at")[:200]

        context = {
            "active_tab": "gaps",
            "status": status,
            "q": q,
            "gaps": gaps,
        }
        return render(request, self.template_name, context)
class StaffGapDetailView(StaffRequiredMixin, View):
    template_name = "staff/gaps_detail.html"

    def get(self, request, gap_id: int):
        gap = get_object_or_404(KnowledgeGap, id=gap_id)
        events = gap.events.order_by("-created_at")[:50]
        reason_counts = (
            gap.events.values("reason")
            .annotate(c=Count("id"))
            .order_by("-c")
        )
        context = {
            "active_tab": "gaps",
            "gap": gap,
            "events": events,
            "reason_counts": reason_counts,
        }
        return render(request, self.template_name, context)
class StaffGapUpdateView(StaffRequiredMixin, View):
    """
    Minimaler Update-Endpoint ohne Forms:
    status, priority, assigned_to, title
    """
    def post(self, request, gap_id: int):
        gap = get_object_or_404(KnowledgeGap, id=gap_id)

        title = (request.POST.get("title") or "").strip()
        status = request.POST.get("status") or gap.status
        priority = request.POST.get("priority")
        assigned_to_id = request.POST.get("assigned_to_id") or ""

        if title:
            gap.title = title

        if status in {"open","in_progress","resolved","ignored"}:
            gap.status = status

        if priority is not None:
            try:
                gap.priority = int(priority)
            except ValueError:
                pass

        if assigned_to_id == "":
            gap.assigned_to = None
        else:
            try:
                gap.assigned_to_id = int(assigned_to_id)
            except ValueError:
                pass

        gap.save(update_fields=["title","status","priority","assigned_to","updated_at"])
        return redirect("staff-gap-detail", gap_id=gap.id)
class StaffGapCreateKBView(StaffRequiredMixin, View):
    """
    Erstellt aus einem KnowledgeGap einen KBEntry (Draft) und verknüpft ihn.
    """
    def post(self, request, gap_id: int):
        gap = get_object_or_404(KnowledgeGap, id=gap_id)

        # Falls schon verknüpft: nicht doppelt erzeugen
        if gap.linked_kb_entry_id:
            messages.info(request, "Zu diesem Gap existiert bereits ein verknüpfter KB-Entwurf.")
            return redirect("staff-gap-detail", gap_id=gap.id)

        # Titel bestimmen
        title = (gap.title or gap.representative_question or "").strip()
        if len(title) > 120:
            title = title[:120].rstrip() + "…"

        # Events für Vorbefüllung
        events = list(gap.events.order_by("-created_at")[:10])

        examples = "\n".join(
            f"- {e.question_redacted.strip()}"
            for e in events
            if (e.question_redacted or "").strip()
        )

        # Top-Sources aus letztem Event (falls vorhanden)
        last_sources = []
        if events:
            last_sources = events[0].top_sources or []

        sources_md = ""
        if last_sources:
            sources_md = "\n".join(
                f"- {s.get('title','Quelle')} ({s.get('source_kind')} #{s.get('source_id')}, score {s.get('score')})"
                + (f", Seite {s.get('page')}" if s.get("page") else "")
                for s in last_sources
            )

        # Draft-Body (Markdown)
        body_md = (
            f"# Problem\n"
            f"Dieses KB-Artikel-Draft wurde aus einer erkannten Wissenslücke (Knowledge Gap #{gap.id}) generiert.\n\n"
            f"**Repräsentative Frage:**\n"
            f"> {gap.representative_question.strip()}\n\n"
            f"# Zielgruppe / Kontext\n"
            f"- (z. B. Endnutzer / Admin / Customer)\n"
            f"- (Produkt/Modul: …)\n\n"
            f"# Lösungsschritte\n"
            f"1. …\n"
            f"2. …\n"
            f"3. …\n\n"
            f"# Häufige Varianten dieser Anfrage\n"
            f"{examples if examples else '- (noch keine Beispiele)'}\n\n"
            f"# Quellen / Hinweise\n"
            f"{sources_md if sources_md else '- (noch keine Quellen-Vorschläge gespeichert)'}\n\n"
            f"# Validierung\n"
            f"- (Wie kann der Kunde prüfen, dass es funktioniert?)\n\n"
            f"# Stand\n"
            f"- Erstellt am {timezone.now().strftime('%d.%m.%Y %H:%M')}\n"
            f"- Gap-Status: {gap.status}\n"
        )

        kb = KBEntry.objects.create(
            title=title or f"Knowledge Gap #{gap.id}",
            body_md=body_md,
            tags=["gap", f"gap:{gap.id}", gap.reason_top],
            status="draft",
            version=1,
            created_by=request.user,
        )

        gap.linked_kb_entry_id = kb.id
        gap.status = "in_progress" if gap.status == "open" else gap.status
        gap.save(update_fields=["linked_kb_entry_id", "status", "updated_at"])

        messages.success(request, f"KB-Entwurf erstellt (KBEntry #{kb.id}) und mit Gap verknüpft.")
        return redirect("staff-gap-detail", gap_id=gap.id)
