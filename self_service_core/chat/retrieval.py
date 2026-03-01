from django.db import connection
from typing import List, Dict, Optional
import json

# ---  Variablen ---
FETCH_MULT = 4  # wir holen k*4, re-ranken dann auf k

# Gewichte: kuratierte KB > Richtlinien > FAQ > Handbücher
KB_STATUS_WEIGHT = {
    "published": 1.35,
    "review": 1.20,
    "draft": 0.95,
    "archived": 0.85,
}

DOC_CATEGORY_WEIGHT = {
    "policy": 1.25,  # verbindlich/regelwerk
    "faq": 1.15,     # kurze support-nahe Antworten
    "manual": 1.05,  # lange Anleitungen
    "other": 1.00,
}

# Quoten: verhindert, dass ein Typ alles dominiert
QUOTA_LIMITS = {
    "kb": 4,   # max KB chunks in k
    "doc": 3,  # max doc chunks in k
}

# ---  Helper-Funktionen ---
def _parse_meta(meta_val) -> Dict:
    if meta_val is None:
        return {}
    if isinstance(meta_val, dict):
        return meta_val
    if isinstance(meta_val, str):
        try:
            return json.loads(meta_val)
        except Exception:
            return {}
    return {}


def _weight_for_passage(p: Dict) -> float:
    kind = (p.get("source_kind") or "other").lower()
    meta = _parse_meta(p.get("meta"))

    if kind == "kb":
        status = (meta.get("status") or "draft").lower()
        return KB_STATUS_WEIGHT.get(status, 1.10)

    if kind == "doc":
        cat = (meta.get("category") or "other").lower()
        return DOC_CATEGORY_WEIGHT.get(cat, 1.00)

    return 1.00


def _select_with_quota(passages: List[Dict], k: int) -> List[Dict]:
    selected: List[Dict] = []
    counters = {key: 0 for key in QUOTA_LIMITS.keys()}

    for p in passages:
        kind = (p.get("source_kind") or "other").lower()

        # Quota nur für definierte kinds anwenden
        if kind in QUOTA_LIMITS:
            if counters[kind] >= QUOTA_LIMITS[kind]:
                continue
            counters[kind] += 1

        selected.append(p)
        if len(selected) >= k:
            break

    # Falls Quota zu streng war: mit besten Resten auffüllen
    if len(selected) < k:
        seen_ids = {p.get("id") for p in selected}
        for p in passages:
            if p.get("id") in seen_ids:
                continue
            selected.append(p)
            if len(selected) >= k:
                break

    return selected


def search_similar(query_vec: List[float],k: int = 6,acl: Optional[List[str]] = None,)-> List[Dict]:
    acl = acl or []
    fetch_k = max(k, k * FETCH_MULT)

    sql = (
        "SELECT id, source_kind, source_id, ord, text, meta, "
        "  1 - (embedding <#> %s::vector) AS score "
        "FROM knowledge_chunk "
        "WHERE (meta->>'acl') IS NULL OR EXISTS ("
        "  SELECT 1 FROM jsonb_array_elements_text(COALESCE(meta->'acl','[]'::jsonb)) AS g "
        "  WHERE g = ANY(%s)"
        ") "
        "ORDER BY embedding <#> %s::vector ASC "
        "LIMIT %s"
    )

    vec = _to_pgvector(query_vec)

    with connection.cursor() as cur:
        cur.execute(sql, [vec, acl, vec, fetch_k])
        rows = cur.fetchall()

    passages: List[Dict] = []
    for r in rows:
        p = {
            "id": r[0],
            "source_kind": r[1],
            "source_id": r[2],
            "ord": r[3],
            "text": r[4],
            "meta": r[5],
            "score": float(r[6]),
        }

        w = _weight_for_passage(p)
        p["weight"] = float(w)
        p["weighted_score"] = p["score"] * w
        passages.append(p)

    # Re-rank: höher ist besser
    passages.sort(key=lambda x: x.get("weighted_score", 0.0), reverse=True)

    # Quota anwenden und final auf k begrenzen
    final = _select_with_quota(passages, k=k)
    return final


def _to_pgvector(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"
