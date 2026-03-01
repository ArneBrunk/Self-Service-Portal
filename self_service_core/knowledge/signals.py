# --- Import Django ---
from django.db import transaction,close_old_connections
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

# --- Import App-Content ---
from knowledge.models import KBEntry, Chunk  
from knowledge.models import KnowledgeGap
from knowledge.ingestion import index_kb_entry  

# --- Import Sonstige Module ---
import threading


# ---  Helper-Funktionen ---
def _delete_existing_kb_chunks(entry_id: int):
    Chunk.objects.filter(source_kind="kb", source_id=entry_id).delete()

@receiver(pre_save, sender=KBEntry)
def kbentry_pre_save_store_old_status(sender, instance: KBEntry, **kwargs):
    """
    Speichert den alten Status auf instance._old_status, damit er im post_save Signal verglichen werden kann.
    """
    if not instance.pk:
        instance._old_status = None
        return

    try:
        old = KBEntry.objects.only("status").get(pk=instance.pk)
        instance._old_status = old.status
    except KBEntry.DoesNotExist:
        instance._old_status = None


@receiver(post_save, sender=KBEntry)
def kbentry_post_save_close_gap_and_reindex(sender, instance: KBEntry, created: bool, **kwargs):
    """
    Wenn status von != published -> published wechselt:
    1) verknüpfte KnowledgeGaps auf resolved setzen
    2) Reindex für KBEntry anstoßen (optional async)
    """
    old_status = getattr(instance, "_old_status", None)
    new_status = instance.status

    published_transition = (old_status != "published" and new_status == "published")
    if not published_transition:
        return


    def _after_commit():
        KnowledgeGap.objects.filter(linked_kb_entry_id=instance.id).exclude(status="resolved").update(status="resolved")

        def reindex_worker(entry_id: int):
            close_old_connections()
            entry = KBEntry.objects.get(id=entry_id)
            _delete_existing_kb_chunks(entry_id)
            index_kb_entry(entry)

        t = threading.Thread(target=reindex_worker, args=(instance.id,), daemon=True)
        t.start()


    transaction.on_commit(_after_commit)
