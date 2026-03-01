# --- Import Django ---
from django.db import connection
# --- Import App-Content ---
from .models import Document, KBEntry
from staff.models import ChatbotConfig
# --- Import Sonstige Module ---
import re
import os
import json
from openai import OpenAI
from typing import List, Dict, Optional

# ---  Variablen ---
EMBEDDING_MODEL = "text-embedding-3-small"
CHAT_MODEL = "gpt-4.1-mini"

# KB eher klein & fokussiert
KB_MAX_CHARS = 1400
KB_OVERLAP_CHARS = 120

# Dokumente je Kategorie (policy > manual > faq etc.)
DOC_CHUNK_CONFIG = {
    "policy": {"max_chars": 2600, "overlap_chars": 260},
    "manual": {"max_chars": 2400, "overlap_chars": 240},
    "faq":    {"max_chars": 1600, "overlap_chars": 160},
    "other":  {"max_chars": 2000, "overlap_chars": 200},
}

DEFAULT_DOC_MAX_CHARS = 2000
DEFAULT_DOC_OVERLAP_CHARS = 200

# ---  Helper-Funktionen ---
def simple_chunk(text: str, max_chars: int = 2000, overlap_chars: int = 0) -> list[str]:
    """
    Absatz-/Überschriftsorientiert chunking mit optionalem Overlap.
    - split an Leerzeilen
    - Buffer bis max_chars
    - Wenn überläuft: Chunk speichern und optional Tail-Overlap übernehmen
    """
    if not text:
        return []

    parts = re.split(r"\n\s*\n", text.strip())
    chunks: list[str] = []
    buf = ""

    for p in parts:
        p = (p or "").strip()
        if not p:
            continue

        candidate = f"{buf}\n\n{p}" if buf else p
        if len(candidate) <= max_chars:
            buf = candidate
            continue

        # Buffer ist "voll", speichere Chunk
        if buf:
            chunks.append(buf)

            # Overlap: Tail aus dem vorherigen Chunk
            tail = ""
            if overlap_chars and len(buf) > overlap_chars:
                tail = buf[-overlap_chars:].strip()

            buf = f"{tail}\n\n{p}".strip() if tail else p
        else:
            # einzelner Absatz größer als max_chars – direkt chunken
            start = 0
            L = len(p)
            while start < L:
                end = min(start + max_chars, L)
                chunks.append(p[start:end])
                if end >= L:
                    break

                if overlap_chars:
                    start = max(0, end - overlap_chars)
                else:
                    start = end

            buf = ""


    if buf:
        chunks.append(buf)

    # Optional: ganz kurze Chunks rausfiltern 
    chunks = [c for c in chunks if len(c.strip()) >= 50]
    return chunks


def embed_texts(texts: List[str], batch_size: int = 64) -> List[List[float]]:
    cfg = ChatbotConfig.get_solo()
    api_key = cfg.openai_api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OpenAI API-Key fehlt.")

    if not texts:
        return []

    client = OpenAI(api_key=api_key)
    out: List[List[float]] = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i+batch_size]
        resp = client.embeddings.create(model=EMBEDDING_MODEL, input=batch)
        out.extend([item.embedding for item in resp.data])

    return out



def index_kb_entry(entry: KBEntry) -> int:
    """
    KB: kleinere, fokussierte Chunks + geringer Overlap.
    """
    chunks = simple_chunk(entry.body_md, max_chars=KB_MAX_CHARS, overlap_chars=KB_OVERLAP_CHARS)
    vectors = embed_texts(chunks)

    verified = (entry.status == "published")

    chunk_meta = [{
        "title": entry.title,
        "kb_entry_id": entry.id,
        "status": entry.status,
        "verified": verified,
        "source_kind": "kb",
        "heading": "Knowledge Base",
        "updated_at": entry.updated_at.isoformat() if getattr(entry, "updated_at", None) else None,
        "chunking": {"max_chars": KB_MAX_CHARS, "overlap_chars": KB_OVERLAP_CHARS},
    } for _ in chunks]

    _insert_chunks("kb", entry.id, chunks, vectors, chunk_meta)
    return len(chunks)


def index_document(doc: Document, pages_text: list[str]) -> int:
    """
    Dokumente (PDF): Chunk-Größe und Overlap abhängig von doc.category.
    Zusätzlich seitenweises Vorgehen (pages_text) für nachvollziehbare meta.page.
    """
    cfg = DOC_CHUNK_CONFIG.get(doc.category or "other", None)
    max_chars = (cfg or {}).get("max_chars", DEFAULT_DOC_MAX_CHARS)
    overlap_chars = (cfg or {}).get("overlap_chars", DEFAULT_DOC_OVERLAP_CHARS)

    all_chunks: list[str] = []
    all_meta: list[dict] = []

    for page_idx, page_text in enumerate(pages_text, start=1):
        page_chunks = simple_chunk(page_text, max_chars=max_chars, overlap_chars=overlap_chars)
        all_chunks.extend(page_chunks)

        all_meta.extend([{
            "page": page_idx,
            "filename": os.path.basename(doc.file.name),
            "doc_id": doc.id,
            "doc_title": doc.title,
            "document_title": doc.title,
            "source_kind": "pdf",  
            "category": doc.category,
            "status": doc.status,
            "updated_at": doc.updated_at.isoformat() if getattr(doc, "updated_at", None) else None,
            "chunking": {"max_chars": max_chars, "overlap_chars": overlap_chars},
        } for _ in page_chunks])

    vectors = embed_texts(all_chunks)
    _insert_chunks("pdf", doc.id, all_chunks, vectors, all_meta) 
    return len(all_chunks)


def _insert_chunks(
    source_kind: str,
    source_id: int,
    chunks: list[str],
    vectors: list[list[float]],
    pages_meta: list[dict] | None = None,
):
    """
    Speichert Chunks + Embeddings in der knowledge_chunk Tabelle.
    meta wird explizit als JSON serialisiert.
    """
    if not chunks:
        return

    if len(chunks) != len(vectors):
        raise ValueError(f"chunks/vectors mismatch: {len(chunks)} vs {len(vectors)}")

    with connection.cursor() as cur:
        for i, (txt, vec) in enumerate(zip(chunks, vectors)):
            meta_dict = pages_meta[i] if pages_meta and i < len(pages_meta) else {}
            meta_json = json.dumps(meta_dict)

            cur.execute(
                """
                INSERT INTO knowledge_chunk (
                    source_kind,
                    source_id,
                    ord,
                    text,
                    meta,
                    embedding
                )
                VALUES (%s, %s, %s, %s, %s::jsonb, %s::vector)
                """,
                [
                    source_kind,
                    source_id,
                    i,
                    txt,
                    meta_json,
                    _to_pgvector(vec),
                ],
            )


def _to_pgvector(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"
