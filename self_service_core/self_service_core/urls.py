# --- Import Django ---
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.routers import DefaultRouter
from django.contrib.auth.views import LogoutView

# --- Import App-Content ---
from knowledge.views import KBViewSet, TempNoticeViewSet
from chat.views import ChatView,ChatPageView
from ingest.views import UploadView, ReindexView
from ingest.views import DocumentUploadPage
from quality.views import  QualityRunStatusView, QualityHumanRatingUpdateView
from users.views import HomeView, CustomerRegisterView, CustomLoginView, CustomerProfileView
from tickets.views import StaffSettingsView
from staff.views import StaffSettingsView, StaffTicketsView, StaffKnowledgeView, StaffMaintenanceView, StaffQualityView, StaffDashboardView, StaffProfileView, StaffPdfUploadView, StaffPdfReindexView, StaffPdfStatusView, StaffQualityQuestionsView, StaffGapListView, StaffGapDetailView, StaffGapUpdateView, StaffGapCreateKBView


router = DefaultRouter()
router.register(r"knowledge/kb", KBViewSet)
router.register(r"knowledge/tempnotices", TempNoticeViewSet)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("staff/dashboard/", StaffDashboardView.as_view(), name="staff-dashboard"),
    path("staff/tickets/", StaffTicketsView.as_view(), name="staff-tickets"),
    path("staff/settings/", StaffSettingsView.as_view(), name="staff-settings"),
    path("staff/profile/", StaffProfileView.as_view(), name="staff-profile"),
    path("staff/knowledge/", StaffKnowledgeView.as_view(), name="staff-kb"),
    path("staff/pdf-upload/", StaffPdfUploadView.as_view(), name="staff-pdf-upload"),
    path("staff/pdf-upload/reindex/<int:pk>/", StaffPdfReindexView.as_view(), name="staff-pdf-reindex"),
    path("staff/pdf-upload/status/", StaffPdfStatusView.as_view(), name="staff-pdf-status"),
    path("staff/maintenance/", StaffMaintenanceView.as_view(), name="staff-maintenance"),
    path("staff/quality/result/<int:result_id>/rate/", QualityHumanRatingUpdateView.as_view(), name="quality-rate-result"),
    path("gaps/", StaffGapListView.as_view(), name="staff-gaps"),
    path("gaps/<int:gap_id>/", StaffGapDetailView.as_view(), name="staff-gap-detail"),
    path("gaps/<int:gap_id>/update/", StaffGapUpdateView.as_view(), name="staff-gap-update"),
    path("gaps/<int:gap_id>/create-kb/", StaffGapCreateKBView.as_view(), name="staff-gap-create-kb"),
    path("api/ingest/upload", UploadView.as_view()),
    path("api/ingest/reindex/<int:pk>", ReindexView.as_view()),
    path('',  HomeView.as_view(), name="landing"),
    path("login/", CustomLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(next_page="landing"), name="logout"),
    path("register/", CustomerRegisterView.as_view(), name="register"),
    path("me/profile/", CustomerProfileView.as_view(), name="customer-profile"),
    path("api/", include(router.urls)),
    path("api/chat", ChatView.as_view()),
    path("chat/", ChatPageView.as_view(), name="chat-page"),
  
]


urlpatterns += [
    path("staff/upload/", DocumentUploadPage.as_view(), name="staff-upload"),
    path("staff/quality/",StaffQualityView.as_view(),name="staff-quality"),
    path("staff/quality/questions/", StaffQualityQuestionsView.as_view(), name="quality-questions"),
    path("staff/quality/status/<int:run_id>/",QualityRunStatusView.as_view(),name="quality-run-status"),
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)