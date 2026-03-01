from django.contrib import admin
from .models import Ticket
from solo.admin import SingletonModelAdmin
from .models import TicketSystemConfig

@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("title", "customer_name", "status", "priority", "created_at")
    list_filter = ("status", "priority")


@admin.register(TicketSystemConfig)
class TicketSystemConfigAdmin(SingletonModelAdmin):
    pass
