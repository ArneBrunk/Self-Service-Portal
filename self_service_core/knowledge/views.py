from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from .models import KBEntry, TempNotice
from .serializers import KBEntrySerializer, TempNoticeSerializer
from staff.mixin import StaffAdminRequiredMixin, StaffRequiredMixin

class KBViewSet(viewsets.ModelViewSet):
    queryset = KBEntry.objects.all()
    serializer_class = KBEntrySerializer
    permission_classes = [IsAuthenticated, StaffAdminRequiredMixin]

class TempNoticeViewSet(viewsets.ModelViewSet):
    queryset = TempNotice.objects.all()
    serializer_class = TempNoticeSerializer
    permission_classes = [IsAuthenticated, StaffAdminRequiredMixin]