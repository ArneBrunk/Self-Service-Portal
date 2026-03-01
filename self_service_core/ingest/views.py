# --- Import Django ---
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.views import View
from django.shortcuts import render, redirect
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
# --- Import App-Content ---
from .serializers import UploadSerializer
from .forms import DocumentUploadForm
# --------------
from knowledge.models import Document
from knowledge.ingestion import index_document
from staff.mixin import StaffAdminRequiredMixin, StaffRequiredMixin
# --- Import Sonstige Module ---
import traceback
from pypdf import PdfReader
try:
    import fitz  
except Exception:
    fitz = None

# ---  Helper-Funktionen ---
def _extract_text(pdf_path: str):
    pages_text, pages_meta = [], []
    # 1) Option: PyMuPDF
    if fitz is not None:
        doc = fitz.open(pdf_path)
        for i in range(len(doc)):
            text = (doc[i].get_text("text") or "").strip()
            if not text:
                continue
            pages_text.append(text)
            pages_meta.append({"page": i+1})
        if pages_text:
            return pages_text, pages_meta

    # 2) Fallback: pypdf
    reader = PdfReader(pdf_path)
    for i, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if not text:
            continue
        pages_text.append(text)
        pages_meta.append({"page": i})

    return pages_text, pages_meta


# --- Views ---
class UploadView(APIView):
    permission_classes = [IsAuthenticated, StaffAdminRequiredMixin]

    def post(self, request):
        ser = UploadSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        doc: Document = ser.save(created_by=request.user)

        try:
            doc.status = "processing"
            doc.index_progress = 5
            doc.index_message = "Extrahiere Text…"
            doc.save(update_fields=["status", "index_progress", "index_message"])

            extracted, pages_meta = _extract_text(doc.file.path)

            if not extracted:
                doc.status = "failed"
                doc.index_progress = 0
                doc.index_message = "Kein Text extrahierbar (PDF evtl. Scan ohne OCR)."
                doc.save(update_fields=["status", "index_progress", "index_message"])
                return Response({"error": "no_text_extracted", "document_id": doc.id}, status=400)

            doc.index_progress = 25
            doc.index_message = f"Indexiere {len(extracted)} Seiten…"
            doc.save(update_fields=["index_progress", "index_message"])

            index_document(doc, extracted, pages_meta)

            doc.status = "published"
            doc.index_progress = 100
            doc.index_message = "Indexierung abgeschlossen."
            doc.save(update_fields=["status", "index_progress", "index_message"])
            return Response({"document_id": doc.id})

        except Exception as e:
            doc.status = "failed"
            doc.index_message = f"{type(e).__name__}: {e}"
            doc.save(update_fields=["status", "index_message"])
            traceback.print_exc()
            return Response(
                {"error": "index_failed", "detail": str(e), "document_id": doc.id},
                status=500
            )

class ReindexView(APIView):
    permission_classes = [IsAuthenticated, StaffAdminRequiredMixin]
    def post(self, request, pk: int):
        doc = Document.objects.get(pk=pk)
        extracted, pages_meta = _extract_text(doc.file.path)
        index_document(doc, extracted, pages_meta)
        return Response(status=202)

class StaffRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_staff

class DocumentUploadPage(LoginRequiredMixin, StaffRequiredMixin, View):
    template_name = "ingest/upload.html"

    def get(self, request):
        form = DocumentUploadForm()
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        form = DocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            doc = form.save(commit=False)
            doc.created_by = request.user
            doc.save()
            extracted, pages_meta = _extract_text(doc.file.path)
            index_document(doc, extracted, pages_meta)
            doc.status = "published"
            doc.save(update_fields=["status"])
            return redirect("upload-success") 
        return render(request, self.template_name, {"form": form})
