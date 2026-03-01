from django.shortcuts import render, redirect , get_object_or_404
from django.views import View
from django.contrib.auth import login, logout
from django.contrib.auth.views import LoginView
from django.urls import reverse_lazy, reverse
from django.contrib import messages
from .forms import LoginForm
from .forms import CustomerProfileForm
from django.views import View
from django.shortcuts import render, redirect
from django.contrib.auth import login
from .forms import CustomerRegisterForm
from .models import Customer, ServicePlan, User
from .utils import generate_customer_id
from staff.models import CompanyProfile
from .mixin import CustomerRequiredMixin


class HomeView(View):
    template_name = "home.html"

    def get(self, request):
        company = CompanyProfile.get_solo()
        return render(request, self.template_name, {"company": company})
class CustomLoginView(LoginView):
    authentication_form = LoginForm
    template_name = "users/login.html"

    def get_success_url(self):

        user = self.request.user

        # 1) Mitarbeiter/Admin
        if hasattr(user, "staff"):
            # Admin → Settings
            if user.staff.role == "admin":
                return reverse_lazy("staff-dashboard")
            
            # Mitarbeiter → Tickets / Dashboard
            return reverse_lazy("staff-dashboard")

        # 2) Kunde
        return reverse_lazy("chat-page")

class CustomLogoutView(View):
    def post(self, request):
        logout(request)
        return redirect("landing")

class CustomerProfileView(CustomerRequiredMixin, View):
    template_name = "users/profile.html"

    def get(self, request):
        form = CustomerProfileForm(instance=request.user)
        return render(request, self.template_name, {
            "form": form,
            "service_level": request.user.customer.service_plan,
        })

    def post(self, request):
        # Account löschen?
        if "delete_account" in request.POST:
            user = request.user
            # Soft-Delete: User deaktivieren (sicherer für Logs/Referenzen)
            user.is_active = False
            user.save(update_fields=["is_active"])

            logout(request)
            messages.success(request, "Dein Account wurde deaktiviert.")
            return redirect("landing")  # oder deine Startseiten-URL

        # Profil aktualisieren
        form = CustomerProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Deine Daten wurden aktualisiert.")
            return redirect("customer-profile")

        return render(request, self.template_name, {
            "form": form,
            "service_level": request.user.customer.service_plan,
        })
    
class CustomerRegisterView(View):
    template_name = "users/register.html"

    def get(self, request):
        form = CustomerRegisterForm()
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        form = CustomerRegisterForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        # User anlegen
        user: User = form.save(commit=False)
        user.save()

        # Service-Level "free" holen
        free_plan = ServicePlan.objects.filter(code="free").first()

        # Kundennummer + Customer erstellen
        customer_id = generate_customer_id()
        Customer.objects.create(
            user=user,
            customer_id=customer_id,
            service_plan=free_plan,
        )

        # Auto-Login und weiter zum Chat
        login(request, user)
        return redirect("chat-page")
