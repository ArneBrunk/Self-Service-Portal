# --- Import Django ---
from django.utils.timezone import now
# --- Import App-Content ---
from tickets.models import TicketSystemConfig
# --- Import Sonstige Module ---
import requests

# ---  Helper-Funktionen ---
def format_sources(sources):
    """
    Formatiert Quellen kurz: [S1] Titel – Seite X – (score 0.87)
    Optional Snippet (gekürzt)
    """
    if not sources:
        return ""

    lines = []
    for i, s in enumerate(sources, start=1):
        title = (s or {}).get("title") or "Quelle"
        page = (s or {}).get("page")
        heading = (s or {}).get("heading")
        score = (s or {}).get("score")
        snippet = ((s or {}).get("snippet") or "").strip()

        loc = ""
        if page:
            loc = f"Seite {page}"
        elif heading:
            loc = str(heading)

        meta = []
        if loc:
            meta.append(loc)
        if score is not None:
            try:
                meta.append(f"score {float(score):.3f}")
            except Exception:
                pass

        meta_txt = f" – {' – '.join(meta)}" if meta else ""

        lines.append(f"[S{i}] {title}{meta_txt}")

        if snippet:
            lines.append(f"    \"{snippet[:300]}\"")

    return "\n".join(lines)


def format_chat_history(session):
    """
    Baut einen gut lesbaren Chatverlauf:
    [Zeit] Kunde/Bot: Nachricht
    + bei Bot: Quellenblock (falls vorhanden)
    """
    lines = []
    for msg in session.messages.order_by("created_at"):
        role = "Kunde" if msg.role == "user" else "Bot"
        timestamp = msg.created_at.strftime("%d.%m.%Y %H:%M")
        lines.append(f"[{timestamp}] {role}: {msg.content}")
        if msg.role != "user":
            src_block = format_sources(getattr(msg, "sources", None))
            if src_block:
                lines.append("  Quellen:")
                lines.append(src_block)

        lines.append("")  

    return "\n".join(lines).strip()



def export_ticket_to_external(ticket):
    """
    Exportiert ein Ticket an Zammad.
    Nutzt cfg.api_url als Ticket-Endpoint (z. B. https://.../api/v1/tickets)
    und cfg.api_key als Token.
    Gibt (success: bool, message: str) zurück.
    """
    cfg = TicketSystemConfig.get_solo()

    if not cfg.enabled:
        return False, "Ticket-System Integration ist deaktiviert."

    if not cfg.api_url or not cfg.api_key:
        return False, "API-URL oder API-Key nicht konfiguriert."

    # Zammad-Auth (Standard):
    #   Authorization: Token token=XYZ
    headers = {
        "Authorization": f"Bearer {cfg.api_key}",
        "Content-Type": "application/json",
    }
    # WENN Ticket ein Feld session_id hat:
    if ticket.session_id:
        from chat.models import ChatSession
        session = ChatSession.objects.get(id=ticket.session_id)
        chat_history = format_chat_history(session)
    else:
        chat_history = "(kein Chatverlauf verfügbar)"
    # Basis-URL aus Ticket-Endpoint ableiten
    # cfg.api_url z. B.: https://host/api/v1/tickets
    tickets_url = cfg.api_url.rstrip("/")
    if tickets_url.endswith("/tickets"):
        base_api_url = tickets_url[: -len("/tickets")]
    else:
        base_api_url = tickets_url

    # Kundendaten aus dem Ticket
    customer_email = getattr(ticket, "customer_email", None)
    customer_name = getattr(ticket, "customer_name", "") or "Unknown"
    customer_id = None

    try:
        if customer_email:
            search_params = {"query": f"email:{customer_email}"}
        else:
            search_params = {"query": customer_name}

        search_resp = requests.get(
            f"{base_api_url}/users/search",
            headers=headers,
            params=search_params,
            timeout=10,
        )

        if search_resp.status_code == 200:
            try:
                users = search_resp.json()
            except ValueError:
                users = []

            if isinstance(users, list) and users:
                customer_id = users[0].get("id")
    except requests.RequestException:
        customer_id = None

    if customer_id is None:
        parts = customer_name.split(" ", 1)
        firstname = parts[0]
        lastname = parts[1] if len(parts) > 1 else ""

        user_payload = {
            "firstname": firstname,
            "lastname": lastname or "Customer",
            "email": customer_email,
            "role_ids": [3],
        }

        try:
            create_resp = requests.post(
                f"{base_api_url}/users",
                json=user_payload,
                headers=headers,
                timeout=10,
            )
        except requests.RequestException as e:
            return False, f"Fehler beim Erstellen des Customers in Zammad: {e}"

        if create_resp.status_code not in (200, 201):
            return (
                False,
                f"Fehler beim Erstellen des Customers in Zammad: "
                f"HTTP {create_resp.status_code} – {create_resp.text}",
            )

        try:
            created_user = create_resp.json()
        except ValueError:
            return False, "Customer in Zammad erstellt, aber Response konnte nicht gelesen werden."

        customer_id = created_user.get("id")
        if not customer_id:
            return False, "Customer in Zammad erstellt, aber keine ID erhalten."

    subject = f"[{ticket.priority.upper()}] {ticket.title}"
    body_text = (
        f"Kunde: {ticket.customer_name}\n"
        f"Erstellt: {ticket.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        f"Status: {ticket.status}\n"
        f"Priorität: {ticket.priority}\n\n"
        "Chatverlauf:\n"
        "---------------------------------------------\n"
        f"{chat_history}\n"
    )
    payload = {
        "title": ticket.title,
        "group": "Users",
        "customer_id": customer_id,
        "article": {
            "subject": subject,
            "body": body_text,
            "type": "note",
            "internal": False,
        },
    }

    try:
        resp = requests.post(cfg.api_url, json=payload, headers=headers, timeout=10)
    except requests.RequestException as e:
        return False, f"Request-Fehler beim Ticket-Export: {e}"

    if resp.status_code in (200, 201):
        external_id = None
        try:
            data = resp.json()
            external_id = data.get("id") or data.get("number")
        except ValueError:
            external_id = None

        ticket.exported = True
        ticket.exported_at = now()
        ticket.status ="in_progress"
        if external_id:
            ticket.external_id = external_id
            ticket.save(update_fields=["exported", "exported_at", "external_id", "status"])
            
        else:
            ticket.save(update_fields=["exported", "exported_at"])

        return True, f"Ticket erfolgreich an Zammad exportiert (ID: {external_id or 'unbekannt'})."

    return False, f"Fehler beim Zammad-Export: HTTP {resp.status_code} – {resp.text}"


def close_ticket_in_external(ticket):
    """
    Schließt ein bereits exportiertes Ticket in Zammad.
    Setzt dort den State z. B. auf 'closed' und aktualisiert das lokale Ticket.
    """
    cfg = TicketSystemConfig.get_solo()

    if not cfg.enabled:
        return False, "Ticket-System Integration ist deaktiviert."

    if not cfg.api_url or not cfg.api_key:
        return False, "API-URL oder API-Key nicht konfiguriert."

    if not ticket.external_id:
        return False, "Ticket hat keine externe Zammad-ID."

    base_url = cfg.api_url.rstrip("/")  
    url = f"{base_url}/{ticket.external_id}"

    headers = {
        "Authorization": f"Bearer {cfg.api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "state": "closed",
    }

    try:
        resp = requests.put(url, json=payload, headers=headers, timeout=10)
    except requests.RequestException as e:
        return False, f"Request-Fehler: {e}"

    if resp.status_code in (200, 201):
        ticket.status = "solved"
        ticket.save(update_fields=["status"])
        return True, "Ticket in Zammad geschlossen und lokal auf 'Erledigt' gesetzt."

    return False, f"Fehler beim Schließen in Zammad: HTTP {resp.status_code} – {resp.text}"