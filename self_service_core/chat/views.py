# --- Import Django ---#Import Django
from django.utils.timezone import now
from django.utils import timezone
from django.contrib import messages
from django.shortcuts import redirect, get_object_or_404,render, redirect
from django.views import View
from django.urls import reverse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from users.mixin import CustomerRequiredMixin

# --- Import App-Content ---
from .models import ChatSession, ChatMessage
from .retrieval import search_similar
from .prompts import SYSTEM_PROMPT, USER_TEMPLATE, render_context, USER_TEMPLATE_NORAG
from .forms import ChatForm
#--------------
from knowledge.ingestion import embed_texts, EMBEDDING_MODEL, CHAT_MODEL
from knowledge.models import TempNotice
from knowledge.gaps import log_knowledge_gap
from staff.models import ChatbotConfig
from quality.eval_utils import extract_cited_indices, has_valid_citation_markers
from users.models import Customer

# --- Import Sonstige Module ---
from openai import OpenAI
import os
import json
import re
from typing import Optional, Tuple, List, Dict


# ---  Variablen ---
# matcht: [S1, S3, S4] oder [S1,S3,S4] oder [S1, S3,S4] für die Umwandlung in [S1][S2] usw.
_MULTI_CITE_RE = re.compile(r"\[(S\d+(?:\s*,\s*S\d+)+)\]")
_CITE_RE = re.compile(r"\[S(\d+)\]")
DEFAULT_SYSTEM_RAG = SYSTEM_PROMPT
DEFAULT_SYSTEM_NORAG = SYSTEM_PROMPT
DEFAULT_USER_RAG = USER_TEMPLATE
DEFAULT_USER_NORAG = USER_TEMPLATE_NORAG


# ---  Helper-Funktionen ---

def normalize_multi_citations(text: str) -> str:
    """
    Wandelt [S1, S3, S4] -> [S1][S3][S4]
    """
    if not text:
        return text

    def repl(m: re.Match) -> str:
        inner = m.group(1)  # z.B. "S1, S3, S4"
        parts = [p.strip() for p in inner.split(",")]
        parts = [p for p in parts if p]  
        return "".join(f"[{p}]" for p in parts)

    return _MULTI_CITE_RE.sub(repl, text)


def parse_meta_loose(raw_meta):
    """
    Vereinheitlicht Meta-Parsing (robust gegen JSON als String / doppelt gequotet etc.)
    """
    if isinstance(raw_meta, str):
        try:
            return json.loads(raw_meta)
        except Exception:
            # "doppelt gequotete" JSON-Strings o.ä. versuchen zu reparieren
            try:
                fixed = raw_meta.strip()
                if fixed.startswith('"') and fixed.endswith('"'):
                    fixed = fixed[1:-1]
                fixed = fixed.replace('""', '"')
                return json.loads(fixed)
            except Exception:
                return {}
    elif isinstance(raw_meta, dict):
        return raw_meta
    return {}


def src_meta(p):
    """
    Einheitliche Passage->Source-Meta Normalisierung.
    """
    meta = parse_meta_loose(p.get("meta") or {})

    title = (
        meta.get("doc_title")
        or meta.get("document_title")
        or meta.get("filename")
        or meta.get("title")
        or "Quelle"
    )

    return {
        "ord": p.get("ord"),
        "source_kind": p.get("source_kind"),
        "source_id": p.get("source_id"),
        "title": title,
        "page": meta.get("page"),
        "heading": meta.get("heading") or meta.get("section"),
        "score": p.get("score"),
        "snippet": (p.get("text") or "")[:400],
    }


def build_history_messages(session: Optional[ChatSession],*, max_turns: int = 6, current_user_text: Optional[str] = None) -> list[dict]:
    """
    Baut LLM-Messages aus der Session-History.
    """
    if not session:
        return []

    qs = session.messages.order_by("-created_at")[: max_turns * 2]
    msgs = list(reversed(qs))  # chronologisch

    # Falls die letzte Message die gerade gespeicherte User-Message ist -> entfernen
    if current_user_text and msgs:
        last = msgs[-1]
        if last.role == "user" and (last.content or "").strip() == (current_user_text or "").strip():
            msgs = msgs[:-1]

    out = []
    for m in msgs:
        if m.role not in ("user", "assistant"):
            continue
        if m.content:
            out.append({"role": m.role, "content": m.content})
    return out


def sanitize_citations_keep_valid(answer: str, max_sources: int) -> tuple[str, list[int]]:
    """
    Entfernt ungültige Marker (z.B. [S7] bei nur 6 Quellen) und gibt die gültigen zitierten Indizes zurück.
    """
    if not answer:
        return answer, []

    cited = sorted(extract_cited_indices(answer))
    cited_valid = [i for i in cited if 1 <= i <= max_sources]

    def repl(m):
        idx = int(m.group(1))
        return m.group(0) if 1 <= idx <= max_sources else ""

    cleaned = _CITE_RE.sub(repl, answer)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned, cited_valid


def build_prompts(cfg: ChatbotConfig,*,rag_enabled: bool,passages_present: bool,question: str,context: str,) -> tuple[str, str]:
    """
    Liefert (system_prompt, user_prompt) basierend auf Settings (cfg) und Modus.
    - RAG: nutzt cfg.system_prompt_rag / cfg.user_template_rag
    - No-RAG: nutzt cfg.system_prompt_norag / cfg.user_template_norag
    - Fallback auf Defaults, falls Feld leer
    """
    if rag_enabled and passages_present:
        base_system = (getattr(cfg, "system_prompt_rag", "") or "").strip() or DEFAULT_SYSTEM_RAG
        user_tmpl = (getattr(cfg, "user_template_rag", "") or "").strip() or DEFAULT_USER_RAG
        user_prompt = user_tmpl.format(question=question, context=context)
    else:
        base_system = (getattr(cfg, "system_prompt_norag", "") or "").strip() or DEFAULT_SYSTEM_NORAG
        user_tmpl = (getattr(cfg, "user_template_norag", "") or "").strip() or DEFAULT_USER_NORAG
        user_prompt = user_tmpl.format(question=question)

    system_prompt = (
        f"{base_system}\n\n"
        f"Bot name: {cfg.bot_name}. "
        f"Role: {cfg.bot_role}. "
        f"Tone: {cfg.get_conversation_tone_display()}."
    )
    return system_prompt, user_prompt


def remap_citations(answer: str, used_old_indices: list[int]) -> tuple[str, dict[int,int]]:
    """
    used_old_indices: z.B. [4, 6] (alte Indizes aus sources_all)
    Return: (answer_remapped, mapping old->new)
    """
    mapping = {old: new for new, old in enumerate(used_old_indices, start=1)}

    def repl(m):
        old = int(m.group(1))
        if old in mapping:
            return f"[S{mapping[old]}]"
        # Marker, der nicht zu den verwendeten Quellen gehört -> entfernen
        return ""

    return _CITE_RE.sub(repl, answer), mapping


def is_non_answer(answer: str) -> bool:
    markers = [
        "keine information",
        "nicht bekannt",
        "liegen mir nicht vor",
        "kann ich nicht beantworten",
    ]
    a = (answer or "").lower()
    return any(m in a for m in markers)


def compute_escalation(*,q: str,answer: str, passages: List[Dict], cfg: ChatbotConfig,) -> Tuple[bool, Optional[str], float]:
    """
    Returns:
      should_escalate (bool),
      reason (str|None) in {"low_retrieval","keyword","non_answer"},
      best_score (float)
    """
    best_score = max((p.get("score", 0.0) for p in passages), default=0.0)
    threshold = (cfg.confidence_threshold or 75) / 100.0

    user_text_lower = (q or "").lower()
    keyword_hit = any(kw in user_text_lower for kw in cfg.escalation_keywords_list())

    if keyword_hit:
        return True, "keyword", best_score

    if is_non_answer(answer):
        return True, "non_answer", best_score

    if best_score < threshold:
        return True, "low_retrieval", best_score

    return False, None, best_score


def call_llm(system_prompt: str,user_prompt: str,cfg: Optional[ChatbotConfig] = None,*,history_messages: Optional[list[dict]] = None,) -> str:
    api_key = cfg.openai_api_key or os.environ.get("OPENAI_API_KEY") if cfg else os.environ.get("OPENAI_API_KEY")

    if not api_key:
        return "OpenAI API-Key fehlt. Bitte im Admin-Bereich hinterlegen."

    client = OpenAI(api_key=api_key)

    temperature = 0.2
    max_tokens = 600

    if cfg:
        temperature = max(0.0, min(1.0, cfg.creativity_level or 0.2))
        if cfg.response_length == "short":
            max_tokens = 300
        elif cfg.response_length == "detailed":
            max_tokens = 1200

    messages_payload = [{"role": "system", "content": system_prompt}]
    if history_messages:
        messages_payload.extend(history_messages)
    messages_payload.append({"role": "user", "content": user_prompt})

    response = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=messages_payload,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content.strip()



def generate_answer_for_question(q: str,request_user,cfg: Optional[ChatbotConfig] = None,*,session: Optional[ChatSession] = None,):
    # eventuell aktivierte Störungsmeldung prüfen
    active = TempNotice.objects.filter(enabled=True, starts_at__lte=now(), ends_at__gte=now()).order_by("-priority")
    notice = active.first() if active.exists() else None
    if notice and notice.mode == "override":
        # passages leer, esc leer
        return notice.body, [], notice, [], (False, None, 0.0), 0.0

    cfg = cfg or ChatbotConfig.get_solo()

    # Customer-Chat: IMMER RAG + ZITATION
    rag_enabled = True
    citations_required = True

    #History aufbauen (max 6 Turns + aktuelle User-Message, damit LLM Kontext hat, aber nicht zu lang wird)
    history = build_history_messages(session, max_turns=6, current_user_text=q)

    # Retrieval NUR wenn RAG enabled (Customer-Chat ist immer RAG)
    q_vec = embed_texts([q])[0]
    acl = getattr(request_user, "acl_groups", []) if request_user and request_user.is_authenticated else []
    passages = search_similar(q_vec, k=6, acl=acl)

    sources_all = [src_meta(p) for p in passages]
    context = render_context(sources_all)

    system_prompt, user_prompt = build_prompts(
        cfg,
        rag_enabled=rag_enabled,
        passages_present=bool(passages),
        question=q,
        context=context,
    )

    answer = call_llm(system_prompt, user_prompt, cfg, history_messages=history)
    answer = normalize_multi_citations(answer)

    # Notice prepend/append
    if notice and notice.mode in {"prepend", "append"}:
        answer = (notice.body + "\n\n" + answer) if notice.mode == "prepend" else (answer + "\n\n" + notice.body)

    # Quellen auf zitierte reduzieren + Marker remappen (wenn RAG + Zitationspflicht)
    used_sources = []
    if citations_required and sources_all:
        # Erst ungültige Marker entfernen, gültige bestimmen
        answer, cited_valid = sanitize_citations_keep_valid(answer, len(sources_all))
        markers_ok = has_valid_citation_markers(answer, len(sources_all)) if sources_all else False

        if cited_valid and markers_ok:
            used_sources = [s for i, s in enumerate(sources_all, start=1) if i in set(cited_valid)]
            answer, _mapping = remap_citations(answer, cited_valid)
        else:
            # Wenn Marker kaputt: keine falschen Quellen anzeigen, Marker entfernen
            used_sources = []
            answer = _CITE_RE.sub("", answer).strip()

    # Eskalation IMMER berechnen (auch Staff), aber Ticket nur bei Non-Staff
    threshold = (cfg.confidence_threshold or 75) / 100.0
    should_escalate, reason, best_score = (False, None, 0.0)
    if cfg.auto_escalation_enabled:
        should_escalate, reason, best_score = compute_escalation(q=q, answer=answer, passages=passages, cfg=cfg)
    return answer, used_sources, notice, passages, (should_escalate, reason, best_score), threshold


# --- Views ---
class ChatView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        q = request.data.get("message", "").strip()
        rag_enabled = bool(request.data.get("rag_enabled", True))
        citations_required = bool(request.data.get("citations_required", True))

        if not rag_enabled:
            citations_required = False

        if not q:
            return Response({"error": "message required"}, status=400)

        # 1) Temporäre Notices prüfen
        active = TempNotice.objects.filter(
            enabled=True, starts_at__lte=now(), ends_at__gte=now()
        ).order_by("-priority")
        notice = active.first() if active.exists() else None
        if notice and notice.mode == "override":
            return Response({"answer": notice.body, "sources": ["[override: temp notice]"]})

        cfg = ChatbotConfig.get_solo()

        # 2) Retrieval NUR wenn rag_enabled
        passages = []
        ctx_passages = []
        context = ""

        if rag_enabled:
            q_vec = embed_texts([q])[0]
            acl = getattr(request.user, "acl_groups", []) if request.user and request.user.is_authenticated else []
            k = int(request.data.get("top_k", 6))
            k = max(1, min(k, 20))
            passages = search_similar(q_vec, k=k, acl=acl)

            ctx_passages = [src_meta(p) for p in passages]
            context = render_context(ctx_passages)

        # 3) Prompts aus Settings
        system_prompt, user_prompt = build_prompts(
            cfg,
            rag_enabled=rag_enabled,
            passages_present=bool(passages),
            question=q,
            context=context,
        )
        sess = None
        session_id = request.data.get("session_id")
        is_staff_user = bool(request.user and request.user.is_authenticated and request.user.is_staff)

        if session_id and request.user and request.user.is_authenticated and (not is_staff_user):
            try:
                sess = ChatSession.objects.get(id=session_id, user=request.user)
            except ChatSession.DoesNotExist:
                sess = None

        history = build_history_messages(sess, max_turns=6, current_user_text=q) if sess else []

        answer = call_llm(system_prompt, user_prompt, cfg, history_messages=history)
        answer = normalize_multi_citations(answer)

        # 4) Notice prepend/append
        if notice and notice.mode in {"prepend", "append"}:
            answer = (notice.body + "\n\n" + answer) if notice.mode == "prepend" else (answer + "\n\n" + notice.body)

        # 4.5) Quellen auf zitierte reduzieren + Marker remappen (wenn RAG + Zitationspflicht)
        if rag_enabled and citations_required and ctx_passages:
            answer, cited_valid = sanitize_citations_keep_valid(answer, len(ctx_passages))
            markers_ok = has_valid_citation_markers(answer, len(ctx_passages))

            if cited_valid and markers_ok:
                used_sources = [s for i, s in enumerate(ctx_passages, start=1) if i in set(cited_valid)]
                answer, _mapping = remap_citations(answer, cited_valid)
                ctx_passages = used_sources
            else:
                ctx_passages = []
                answer = _CITE_RE.sub("", answer).strip()

        # 5) Session/Message speichern nur für Nicht-Staff 
        if not is_staff_user:
            if session_id and sess is None:
                try:
                    sess = ChatSession.objects.get(id=session_id, user=request.user)
                except ChatSession.DoesNotExist:
                    sess = None

            if sess is None and request.user and request.user.is_authenticated:
                sess = ChatSession.objects.create(user=request.user, status="open")

            ChatMessage.objects.create(session=sess, role="user", content=q)
            ChatMessage.objects.create(session=sess, role="assistant", content=answer, sources=ctx_passages)

        # 6) Eskalation IMMER berechnen (auch Staff), aber Ticket nur bei Non-Staff
        should_escalate = False
        reason = None
        best_score = 0.0
        threshold = (cfg.confidence_threshold or 75) / 100.0
        ticket_id = None

        if cfg.auto_escalation_enabled:
            should_escalate, reason, best_score = compute_escalation(
                q=q,
                answer=answer,
                passages=passages if rag_enabled else [],
                cfg=cfg,
            )

        if (not is_staff_user) and should_escalate:
            from tickets.models import Ticket

            ticket = Ticket.objects.create(
                title=q[:120],
                customer_name=(
                    request.user.get_full_name()
                    or request.user.username
                    or "Anonymous"
                ) if request.user.is_authenticated else "Anonymous",
                status="escalated",
                priority="high",
            )
            ticket_id = ticket.id

            log_knowledge_gap(
                question=q,
                reason=reason or "other",
                passages=passages if rag_enabled else [],
                best_score=best_score,
                threshold=threshold,
                user_id=request.user.id if request.user and request.user.is_authenticated else None,
                session_id=sess.id if sess else None,
                ticket_id=ticket_id,
                meta={"channel": "api", "rag_enabled": rag_enabled},
            )

        return Response({
            "answer": answer,
            "sources": ctx_passages,
            "session_id": sess.id if sess else None,
            "escalated": should_escalate,
            "escalation_reason": reason,
            "ticket_id": ticket_id,
        })


class ChatPageView(CustomerRequiredMixin, View):
    template_name = "chat/chat_page.html"

    def get(self, request):
        sessions = ChatSession.objects.filter(user=request.user).order_by("-created_at")

        # Neuer Chat explizit angefordert ODER noch keine Session vorhanden
        if request.GET.get("new") == "1" or not sessions.exists():
            cfg = ChatbotConfig.get_solo()
            greeting = cfg.greeting_message or "Hello! I'm your support assistant. How can I help you?"

            # neue Session anlegen
            new_session = ChatSession.objects.create(
                user=request.user,
                status="open",
                greeting_sent=True,  
            )

            # Greeting sofort als erste Bot-Nachricht speichern
            ChatMessage.objects.create(
                session=new_session,
                role="assistant",
                content=greeting,
                sources=[],         
            )

            # danach auf diese Session umleiten
            return redirect(f"{reverse('chat-page')}?session={new_session.id}")

        # aktive Notices holen & nach Severity + Priority sortieren
        notices_qs = TempNotice.objects.filter(
            enabled=True,
            starts_at__lte=now(),
            ends_at__gte=now(),
        )

        notices = list(notices_qs)
        severity_order = {"critical": 3, "warning": 2, "info": 1}
        notices.sort(
            key=lambda n: (severity_order.get(n.severity, 0), n.priority),
            reverse=True,
        )

        # bestehende Session auswählen
        selected_id = request.GET.get("session")
        if selected_id:
            try:
                selected_session = sessions.get(id=selected_id)
            except ChatSession.DoesNotExist:
                selected_session = sessions.first()
        else:
            selected_session = sessions.first()

        messages = selected_session.messages.order_by("created_at") if selected_session else []

        form = ChatForm()
        return render(request, self.template_name, {
            "sessions": sessions,
            "selected_session": selected_session,
            "messages": messages,
            "form": form,
            "active_notices": notices,
        })

    def post(self, request, *args, **kwargs):
        session_id = request.POST.get("session_id")
        selected_session = get_object_or_404(ChatSession, id=session_id)

        if selected_session.user_id != request.user.id:
            return redirect("chat-page")

        # 1) Chat schließen
        if request.POST.get("close_session") == "1":
            if selected_session.status != "done":
                selected_session.status = "done"
                selected_session.save(update_fields=["status", "updated_at"])
            return redirect(f"{request.path}?session={selected_session.id}")

        # 2) Bewertung speichern
        if request.POST.get("rate_session") == "1":
            if selected_session.status != "done":
                messages.error(request, "Bitte beende zuerst den Chat, bevor du bewertest.")
                return redirect(f"{request.path}?session={selected_session.id}")

            if selected_session.rating is not None:
                messages.info(request, "Dieser Chat wurde bereits bewertet.")
                return redirect(f"{request.path}?session={selected_session.id}")

            try:
                rating = int(request.POST.get("rating", "0"))
            except ValueError:
                rating = 0

            rating_text = (request.POST.get("rating_text") or "").strip()

            if rating < 1 or rating > 5:
                messages.error(request, "Bitte wähle eine Bewertung von 1 bis 5 Sternen.")
                return redirect(f"{request.path}?session={selected_session.id}")

            selected_session.rating = rating
            selected_session.rating_text = rating_text
            selected_session.rated_at = timezone.now()
            selected_session.save(update_fields=["rating", "rating_text", "rated_at"])

            messages.success(request, "Danke! Deine Bewertung wurde gespeichert.")
            return redirect(f"{request.path}?session={selected_session.id}")

        # 3) Normale Chat-Nachricht senden (wenn Session offen)
        if selected_session.status == "done":
            messages.info(request, "Dieser Chat ist beendet. Starte einen neuen Chat.")
            return redirect(f"{request.path}?session={selected_session.id}")

        form = ChatForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Bitte gib eine Nachricht ein.")
            return redirect(f"{request.path}?session={selected_session.id}")

        q = (form.cleaned_data.get("message") or "").strip()
        if not q:
            messages.error(request, "Bitte gib eine Nachricht ein.")
            return redirect(f"{request.path}?session={selected_session.id}")

        cfg = ChatbotConfig.get_solo()

        # User message speichern
        ChatMessage.objects.create(session=selected_session, role="user", content=q)

        # Bot answer generieren + speichern
        answer, used_sources, _notice, passages, esc, threshold = generate_answer_for_question(
            q, request.user, cfg=cfg, session=selected_session
        )

        ChatMessage.objects.create(
            session=selected_session,
            role="assistant",
            content=answer,
            sources=used_sources
        )

        should_escalate, reason, best_score = esc
        if should_escalate:
            from tickets.models import Ticket
            ticket = Ticket.objects.create(
                title=q[:120],
                customer = Customer.objects.get(user=request.user),
                customer_name=request.user.get_full_name() or request.user.username or "Anonymous",
                status="escalated",
                priority="high",
                session_id=selected_session.id,
            )
            threshold = (cfg.confidence_threshold or 75) / 100.0

            log_knowledge_gap(
                question=q,
                reason=reason or "other",
                passages=passages,
                best_score=best_score,
                threshold=threshold,
                user_id=request.user.id,
                session_id=selected_session.id,
                ticket_id=ticket.id,
                meta={"channel": "web"},
            )

            # Bot-Info-Nachricht 
            ChatMessage.objects.create(
                session=selected_session,
                role="assistant",
                content=(
                    "📨 **Support-Übergabe**\n\n"
                    "Deine Anfrage konnte nicht eindeutig automatisiert beantwortet werden. "
                    "Wir haben daher ein Support-Ticket für dich erstellt.\n\n"
                    f"**Ticket-ID:** #{ticket.id}\n\n"
                    "Unser Support-Team kümmert sich schnellstmöglich darum."
                ),
                sources=[], 
            )
        return redirect(f"{request.path}?session={selected_session.id}")