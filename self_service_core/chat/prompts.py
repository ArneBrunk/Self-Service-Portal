# ---  Variablen ---
#SYSTEMPROMPT, falls kein Prompt in der Datenbank abgelegt wurde
SYSTEM_PROMPT = (
    "Du bist ein hilfreicher, präziser Supportassistent.\n\n"
    "MODUS-REGELN:\n"
    "1) Wenn Kontextpassagen bereitgestellt sind (RAG=AN):\n"
    "   - Antworte ausschließlich auf Basis der bereitgestellten Kontextpassagen.\n"
    "   - Zitiere jede zentrale Aussage mit Quellenmarkern exakt mit [Sn], wobei n entspricht der Nummer der Quelle im bereitgestellten Kontext\n"
    "   - Wenn die Evidenz nicht reicht: sage das klar und eskaliere.\n\n"
    "2) Wenn KEINE Kontextpassagen bereitgestellt sind (RAG=AUS):\n"
    "   - Du DARFST allgemeines Wissen nutzen, aber:\n"
    "     * Wenn du es nicht sicher weißt, sage das klar.\n"
    "   - Verwende KEINE Quellenmarker [Sx].\n"
    "   - Gib eine kurze Antwort und hänge an:\n"
    "     'Hinweis: Antwort ohne Wissensbasis (RAG aus). Bitte prüfen.'\n"
)


#USER_TEMPLATE, falls kein Template in der Datenbank abgelegt wurde
USER_TEMPLATE = (
    "Frage: {question}\n\n"
    "Kontext:\n{context}\n\n"
    "Richtlinie: Antworte kurz, präzise, sachlich. Keine Spekulation. "
    "Zitiere jede zentrale Aussage mit Quellenmarkern [Sn], wobei n entspricht der Nummer der Quelle im bereitgestellten Kontext"
)

#USER_TEMPLATE, falls kein Template in der Datenbank abgelegt wurde und RAG aus ist
USER_TEMPLATE_NORAG = (
    "Frage: {question}\n\n"
    "Es wurden keine Kontextpassagen bereitgestellt (RAG ist aus).\n"
    "Antworte kurz, präzise.\n"
    "Für die Beantwortung der Frage darfst du keine Gematik-PDF-Dokumente aus dem Netz einsehen.\n"
    "Keine Quellenmarker verwenden.\n"
)


# ---  Helper-Funktionen ---
def render_context(passages):
    lines = []
    for i, p in enumerate(passages, start=1):
        title = p.get("title", "Quelle")
        page = p.get("page")
        page_txt = f", Seite {page}" if page else ""
        snippet = p.get("snippet", "")

        lines.append(
            f"[S{i}] {title}{page_txt}: {snippet}"
        )
    return "\n".join(lines)
