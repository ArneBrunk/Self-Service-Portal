# --- Import Django ---
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin



# --- Klassen ---
class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Erlaubt nur Mitarbeiter/Admins (StaffUser).
    """
    def test_func(self):
        u = self.request.user
        return u.is_authenticated and hasattr(u, "staff") and u.staff.is_active


class StaffAdminRequiredMixin(StaffRequiredMixin):
    """
    Nur Staff-Admins (role=admin).
    """
    def test_func(self):
        u = self.request.user
        if not (u.is_authenticated and hasattr(u, "staff") and u.staff.is_active):
            return False
        return u.staff.role == "admin"
