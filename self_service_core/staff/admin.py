from django.contrib import admin
from .models import StaffUser

@admin.register(StaffUser)
class StaffUserAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "department", "is_active")
    list_filter = ("role", "is_active")
