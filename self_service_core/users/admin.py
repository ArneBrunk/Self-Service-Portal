from django.contrib import admin
from .models import User, Customer, ServicePlan

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("username", "email",  "is_active", "get_customer_number", "get_service_plan")
    list_filter = ("is_active",)

    def get_customer_number(self, obj):
        if hasattr(obj, "customer") and obj.customer:
            return obj.customer.customer_id
        return "-"
    get_customer_number.short_description = "Kundennummer"

    def get_service_plan(self, obj):
        if hasattr(obj, "customer") and obj.customer and obj.customer.service_plan:
            return obj.customer.service_plan.code
        return "-"
    get_service_plan.short_description = "Service-Level"


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = (
        "username",
        "email",
        "customer_id",
        "service_plan_code",
        "is_active",
    )
    list_filter = ("service_plan__code", "user__is_active")
    search_fields = ("user__username", "customer_id", "user__email")

    def username(self, obj):
        return obj.user.username

    def email(self, obj):
        return obj.user.email

    def is_active(self, obj):
        return obj.user.is_active

    def service_plan_code(self, obj):
        return obj.service_plan.code if obj.service_plan else "-"

    username.short_description = "Benutzername"
    email.short_description = "E-Mail"
    is_active.short_description = "Aktiv?"
    service_plan_code.short_description = "Service-Level"
@admin.register(ServicePlan)
class ServicePlanAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "max_daily_messages", "max_monthly_messages", "priority_support")
    search_fields = ("code", "name")