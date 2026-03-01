# --- Import Django ---
import threading
# --- Import App-Content ---
from knowledge.models import Document
from knowledge.ingestion import index_document
from ingest.views import _extract_text

# ---  Helper-Funktionen ---
def run_index_pipeline(document_id):
    doc = Document.objects.get(pk=document_id)

    try:
        # ----------------------------
        # STEP 1 – Extraktion
        # ----------------------------
        doc.status = "extracting"
        doc.index_progress = 20
        doc.index_message = "PDF wird extrahiert…"
        doc.save(update_fields=["status", "index_progress", "index_message"])

        pages_text, pages_meta = _extract_text(doc.file.path)

        if not pages_text:
            raise RuntimeError("PDF enthält keinen extrahierbaren Text.")

        # ----------------------------
        # STEP 2 – Indexing
        # ----------------------------
        doc.status = "indexing"
        doc.index_progress = 50
        doc.index_message = "Inhalt wird indexiert…"
        doc.save(update_fields=["status", "index_progress", "index_message"])
        new_chunks = index_document(doc, pages_text)

        # ----------------------------
        # FINISHED
        # ----------------------------
        doc.status = "indexed"
        doc.index_progress = 100
        doc.index_message = "Indexierung abgeschlossen."
        doc.indexed_chunks = new_chunks
        doc.save(update_fields=[
            "status",
            "index_progress",
            "index_message",
            "indexed_chunks"
        ])

    except Exception as e:
        doc.status = "error"
        doc.index_progress = 0
        doc.index_message = f"Fehler: {str(e)}"
        doc.save(update_fields=["status", "index_progress", "index_message"])


def start_pipeline_async(document_id):
    t = threading.Thread(
        target=run_index_pipeline,
        args=(document_id,),
        daemon=True
    )
    t.start()
