# --- Import Django ---
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

# --- Klassen ---
class CustomerRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Erlaubt nur Kunden (User mit Customer-Objekt).
    """
    def test_func(self):
        u = self.request.user
        return u.is_authenticated and hasattr(u, "customer")
