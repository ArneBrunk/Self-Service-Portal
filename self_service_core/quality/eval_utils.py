import json
import re
from sentence_transformers import SentenceTransformer, util

#_sem_model = SentenceTransformer("all-MiniLM-L6-v2")
_sem_model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")


def semantic_global_similarity_ok(answer: str, expected: str, threshold: float):
    if not answer or not expected:
        return False, 0.0

    emb_answer = _sem_model.encode(answer, convert_to_tensor=True, normalize_embeddings=True)
    emb_expected = _sem_model.encode(expected, convert_to_tensor=True, normalize_embeddings=True)

    similarity = util.cos_sim(emb_answer, emb_expected).item()
    return similarity >= threshold, float(similarity)



def normalize_sources(raw_sources):
    """
    Normalisiert deine Passage-Dicts zu einem stabilen Format für:
    - Template Rendering
    - Citation-Marker Validierung
    """
    norm = []
    for i, p in enumerate(raw_sources or [], start=1):
        meta_raw = p.get("meta") or {}
        if isinstance(meta_raw, str):
            try:
                meta = json.loads(meta_raw)
            except json.JSONDecodeError:
                meta = {}
        elif isinstance(meta_raw, dict):
            meta = meta_raw
        else:
            meta = {}

        text = (p.get("text") or "").strip()
        snippet = text[:400].rstrip() + ("…" if len(text) > 400 else "")

        title = (
            meta.get("doc_title")
            or meta.get("document_title")
            or meta.get("filename")
            or meta.get("title")
            or f"Quelle {i}"
        )

        norm.append({
            "title": title,
            "page": meta.get("page"),
            "heading": meta.get("heading") or meta.get("section"),
            "snippet": snippet,
            "score": float(p.get("score") or 0.0),

            # optional: debug/trace
            "source_kind": p.get("source_kind"),
            "source_id": p.get("source_id"),
            "ord": p.get("ord"),
        })
    return norm


def has_valid_citation_markers(answer: str, n_sources: int) -> bool:
    """
    Validiert Marker nicht nur 'existiert', sondern auch 'ist gueltig'.
    Beispiel: [S1], [S2] ... muss <= n_sources sein.
    """
    if not answer or n_sources <= 0:
        return False
    markers = {int(m) for m in re.findall(r"\[S(\d+)\]", answer)}
    return bool(markers) and all(1 <= k <= n_sources for k in markers)


def extract_cited_indices(answer: str) -> set[int]:
    """
    Extrahiert zitierte Source-Indizes aus Markern wie [S1], [S2]...
    Gibt 1-basierte Indizes zurück.
    """
    if not answer:
        return set()
    return {int(x) for x in re.findall(r"\[S(\d+)\]", answer)}



def filter_defaults_for_model(model_cls, defaults: dict) -> dict:
    """
    Verhindert 'Invalid field name(s)...' bei update_or_create,
    falls DB-Felder (noch) nicht existieren.
    """
    allowed = {f.name for f in model_cls._meta.get_fields() if hasattr(f, "attname")}
    return {k: v for k, v in defaults.items() if k in allowed}


def _chunks(text: str, max_len: int = 300):
    text = (text or "").strip()
    if not text:
        return []

    # 1) Grobe Trennung auch bei ; , Zeilenumbrüchen
    parts = re.split(r"[;\n]+", text)

    # 2) Danach optional feinere Satztrennung
    sents = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        # splitte zusätzlich auf Punkt/!/?
        sents.extend(re.split(r"(?<=[.!?])\s+", p))

    # 3) Chunk-Größenlimit
    chunks, buf = [], ""
    for s in [x.strip() for x in sents if x.strip()]:
        if len(buf) + len(s) + 1 <= max_len:
            buf = (buf + " " + s).strip()
        else:
            if buf:
                chunks.append(buf)
            buf = s
    if buf:
        chunks.append(buf)

    return chunks


def _normalize_for_semantic(text: str) -> str:
    t = (text or "").lower()
    t = re.sub(r"\[s\d+\]", "", t)                 # [S1] entfernen
    t = t.replace(">=", " mindestens ")            # >= umschreiben
    t = t.replace("gb", " gb ")                    # token spacing
    t = re.sub(r"[^a-z0-9äöüß\s/.-]", " ", t)      # Sonderzeichen entschärfen
    t = re.sub(r"\s+", " ", t).strip()
    return t




def semantic_coverage_score(answer: str, expected: str):
    if not answer or not expected:
        return 0.0, 0.0, 0.0

    a_chunks = [_normalize_for_semantic(c) for c in _chunks(answer)]
    e_chunks = [_normalize_for_semantic(c) for c in _chunks(expected)]


    emb_a = _sem_model.encode(a_chunks, convert_to_tensor=True, normalize_embeddings=True)
    emb_e = _sem_model.encode(e_chunks, convert_to_tensor=True, normalize_embeddings=True)

    # Matrix: [len(e_chunks), len(a_chunks)]
    sim = util.cos_sim(emb_e, emb_a)

    # expected -> best answer chunk  (Recall-like)
    recall_like = sim.max(dim=1).values.mean().item()

    # answer -> best expected chunk  (Precision-like)
    precision_like = sim.max(dim=0).values.mean().item()

    if recall_like + precision_like == 0:
        f1_like = 0.0
    else:
        f1_like = 2 * (recall_like * precision_like) / (recall_like + precision_like)

    return recall_like, precision_like, f1_like

def is_semantically_correct_v1(answer: str, expected: str, min_recall=0.75, min_f1=0.72):
    r, p, f1 = semantic_coverage_score(answer, expected)
    ok = (r >= min_recall) and (f1 >= min_f1)
    return ok, {"recall_like": r, "precision_like": p, "f1_like": f1}

def is_semantically_correct_v2(answer: str, expected: str,
                              min_recall=0.75, min_f1=0.72, min_global=0.78):

    # Coverage (auf normalisiertem Chunking)
    r, p, f1 = semantic_coverage_score(answer, expected)

    # Global (auch normalisieren!)
    a_norm = _normalize_for_semantic(answer)
    e_norm = _normalize_for_semantic(expected)
    _, global_sim = semantic_global_similarity_ok(a_norm, e_norm, threshold=min_global)

    # Extra Signal: bester Satzmatch (hilft bei Definitionen)
    a_chunks = [_normalize_for_semantic(c) for c in _chunks(answer)]
    e_chunks = [_normalize_for_semantic(c) for c in _chunks(expected)]
    max_pair = 0.0
    if a_chunks and e_chunks:
        emb_a = _sem_model.encode(a_chunks, convert_to_tensor=True, normalize_embeddings=True)
        emb_e = _sem_model.encode(e_chunks, convert_to_tensor=True, normalize_embeddings=True)
        max_pair = util.cos_sim(emb_e, emb_a).max().item()

    # 2-von-3 Gate + Definition-Boost
    passed = sum([
        r >= min_recall,
        f1 >= min_f1,
        global_sim >= min_global,
    ]) >= 2

    if not passed and max_pair >= 0.86 and r >= (min_recall - 0.05):
        passed = True

    return passed, {
        "recall_like": r,
        "precision_like": p,
        "f1_like": f1,
        "global_similarity": float(global_sim),
        "max_pair": float(max_pair),
    }
