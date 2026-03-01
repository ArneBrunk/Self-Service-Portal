# --- Import Django ---
from django.db import connection, transaction
from django.utils import timezone
# --- Import App-Content ---
from .models import KnowledgeGap, KnowledgeGapEvent
from knowledge.ingestion import embed_texts  
# --- Import Sonstige Module ---
import re
import json
from typing import List, Dict, Optional, Tuple

# ---  Variablen ---
RE_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
RE_PHONE = re.compile(r"\b(\+?\d[\d\s().-]{7,}\d)\b")
RE_IDLIKE = re.compile(r"\b([A-Z]{0,3}\d{6,}|KD[-\s]?\d+|KUNDENNR[:\s]?\d+)\b", re.IGNORECASE)


# ---  Helper-Funktionen ---
def redact_pii(text: str) -> str:
    if not text:
        return ""
    t = RE_EMAIL.sub("[EMAIL]", text)
    t = RE_PHONE.sub("[PHONE]", t)
    t = RE_IDLIKE.sub("[ID]", t)
    return t


def normalize_question(text: str) -> str:
    t = (text or "").strip().lower()
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"[“”\"'`]", "", t)
    return t


def _to_pgvector(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


def _top_sources_from_passages(passages: List[Dict], limit: int = 3) -> List[Dict]:
    out = []
    for p in (passages or [])[:limit]:
        meta = p.get("meta") or {}
        # meta kann json-string oder dict sein
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        title = meta.get("doc_title") or meta.get("document_title") or meta.get("filename") or meta.get("title") or "Quelle"
        out.append({
            "title": title,
            "source_kind": p.get("source_kind"),
            "source_id": p.get("source_id"),
            "page": meta.get("page"),
            "score": float(p.get("score") or 0.0),
        })
    return out


def find_similar_gap(embedding: List[float], min_similarity: float = 0.82) -> Optional[int]:
    """
    Sucht den ähnlichsten Gap per pgvector.
    """
    vec = _to_pgvector(embedding)
    sql = """
        SELECT id, 1 - (embedding <#> %s::vector) AS sim
        FROM knowledge_knowledgegap
        WHERE embedding IS NOT NULL
        ORDER BY embedding <#> %s::vector ASC
        LIMIT 1;
    """
    with connection.cursor() as cur:
        cur.execute(sql, [vec, vec])
        row = cur.fetchone()

    if not row:
        return None

    gap_id, sim = int(row[0]), float(row[1])
    if sim >= min_similarity:
        return gap_id
    return None


def set_gap_embedding(gap_id: int, embedding: List[float]) -> None:
    vec = _to_pgvector(embedding)
    sql = "UPDATE knowledge_knowledgegap SET embedding = %s::vector WHERE id = %s;"
    with connection.cursor() as cur:
        cur.execute(sql, [vec, gap_id])

@transaction.atomic
def log_knowledge_gap(*,
    question: str,
    reason: str,
    passages: List[Dict],
    best_score: Optional[float],
    threshold: Optional[float],
    user_id: Optional[int] = None,
    session_id: Optional[int] = None,
    ticket_id: Optional[int] = None,
    min_similarity: float = 0.82,
    meta: Optional[Dict] = None,
) -> Tuple[KnowledgeGap, KnowledgeGapEvent]:
    """
    1) redaction + normalize
    2) embed normalized question
    3) find similar KnowledgeGap by vector similarity
    4) update/create gap + store event
    """
    q_raw = question or ""
    q_red = redact_pii(q_raw)
    q_norm = normalize_question(q_red)

    # Embedding auf normalisiertem Text (reduziert Duplikate)
    emb = embed_texts([q_norm])[0]

    # vektor-basiertes Clustering
    similar_id = find_similar_gap(emb, min_similarity=min_similarity)

    if similar_id:
        gap = KnowledgeGap.objects.select_for_update().get(id=similar_id)
        gap.count = (gap.count or 0) + 1
        gap.last_seen_at = timezone.now()
        gap.reason_top = reason or gap.reason_top
        if not gap.title:
            gap.title = (gap.representative_question[:120] or "").strip()
        gap.save(update_fields=["count", "last_seen_at", "reason_top", "title", "updated_at"])
    else:
        gap = KnowledgeGap.objects.filter(representative_question_norm=q_norm).first()
        if gap:
            gap = KnowledgeGap.objects.select_for_update().get(id=gap.id)
            gap.count += 1
            gap.last_seen_at = timezone.now()
            gap.reason_top = reason or gap.reason_top
            gap.save(update_fields=["count", "last_seen_at", "reason_top", "updated_at"])
        else:
            gap = KnowledgeGap.objects.create(
                title=(q_red[:120] or "").strip(),
                representative_question=q_red,
                representative_question_norm=q_norm,
                status="open",
                priority=50,
                count=1,
                reason_top=reason or "other",
                last_seen_at=timezone.now(),
            )
            set_gap_embedding(gap.id, emb)

    event = KnowledgeGapEvent.objects.create(
        gap=gap,
        question_raw=q_raw,
        question_redacted=q_red,
        reason=reason or "other",
        best_score=best_score,
        threshold=threshold,
        top_sources=_top_sources_from_passages(passages, limit=3),
        meta=meta or {},
        user_id=user_id,
        session_id=session_id,
        ticket_id=ticket_id,
    )

    return gap, event
