# --- Import App-Content ---
from users.models import Customer

# ---  Helper-Funktionen ---
def generate_customer_id() -> str:
    """
    Kundennummer-Generierung: K-000001, K-000002, ...
    """
    last = Customer.objects.order_by("-id").first()

    if last and last.customer_id.startswith("K-"):
        try:
            num = int(last.customer_id.split("-")[1])
        except (IndexError, ValueError):
            num = 0
    else:
        num = 0

    return f"K-{num + 1:06d}"

