from django.views import View
from django.shortcuts import render, redirect
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from tickets.models import Ticket

class StaffOnlyMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_staff


class StaffSettingsView(LoginRequiredMixin, StaffOnlyMixin, View):
    template_name = "staff/tickets.html"

    def get(self, request):
        status_filter = request.GET.get("status", "all")

        qs = Ticket.objects.all().order_by("-created_at")
        if status_filter == "escalated":
            qs = qs.filter(status="escalated")
        elif status_filter == "in_progress":
            qs = qs.filter(status="in_progress")
        elif status_filter == "solved":
            qs = qs.filter(status="solved")

        counts = {
            "all": Ticket.objects.count(),
            "escalated": Ticket.objects.filter(status="escalated").count(),
            "in_progress": Ticket.objects.filter(status="in_progress").count(),
            "solved": Ticket.objects.filter(status="solved").count(),
        }

        context = {
            "tickets": qs,
            "counts": counts,
            "status_filter": status_filter,
            "active_tab": "tickets",  
        }

        return render(request, self.template_name, context)
