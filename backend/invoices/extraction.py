from django.conf import settings
from django.db import transaction
from django.utils import timezone

from audit.models import AuditLog
from .models import ExtractionResult, Invoice
from .policies import ensure_invoice_editable


def queue_invoice_extraction(invoice, actor=None):
    """Queue provider-backed extraction after commit; manual mode remains review-only."""
    if settings.EXTRACTION_PROVIDER == "manual" or not invoice.document_id:
        return None

    with transaction.atomic():
        locked = Invoice.objects.select_for_update().get(id=invoice.id, tenant_id=invoice.tenant_id)
        ensure_invoice_editable(locked)
        if locked.document.tenant_id != locked.tenant_id:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"document": "Source document must belong to this workspace."})
        if locked.status == Invoice.Status.EXTRACTING:
            active = locked.extractions.filter(status__in=["QUEUED", "PROCESSING"]).order_by("-created_at").first()
            if active:
                return active

        extraction = ExtractionResult.objects.create(
            tenant=locked.tenant,
            invoice=locked,
            provider=settings.EXTRACTION_PROVIDER,
            status="QUEUED",
        )
        locked.status = Invoice.Status.EXTRACTING
        locked.save(update_fields=["status", "updated_at"])
        AuditLog.objects.create(
            tenant=locked.tenant,
            actor=actor or locked.uploaded_by,
            action="EXTRACTION_QUEUED",
            object_type="Invoice",
            object_id=str(locked.id),
            metadata={"provider": settings.EXTRACTION_PROVIDER, "extraction_id": str(extraction.id)},
        )
        invoice.status = locked.status

        def dispatch():
            try:
                from .tasks import extract_invoice
                extract_invoice.delay(str(locked.id), str(extraction.id))
            except Exception:
                ExtractionResult.objects.filter(id=extraction.id).update(
                    status="FAILED", updated_at=timezone.now(), output={"warnings": ["Could not queue extraction. Check Redis and the Celery worker."]}
                )
                Invoice.objects.filter(id=locked.id, status=Invoice.Status.EXTRACTING).update(
                    status=Invoice.Status.EXTRACTION_FAILED, updated_at=timezone.now()
                )
                AuditLog.objects.create(
                    tenant=locked.tenant,
                    actor=actor or locked.uploaded_by,
                    action="EXTRACTION_QUEUE_FAILED",
                    object_type="Invoice",
                    object_id=str(locked.id),
                    metadata={"extraction_id": str(extraction.id)},
                )

        transaction.on_commit(dispatch)
        return extraction


def recover_stalled_extractions():
    """Release abandoned jobs for explicit retry; fence out late worker results."""
    from datetime import timedelta
    cutoff = timezone.now() - timedelta(seconds=settings.EXTRACTION_STALE_SECONDS)
    stale = ExtractionResult.objects.filter(status__in=["QUEUED", "PROCESSING"], updated_at__lt=cutoff).values_list("id", "invoice_id")
    recovered = 0
    for extraction_id, invoice_id in stale.iterator():
        with transaction.atomic():
            invoice = Invoice.objects.select_for_update().get(id=invoice_id)
            job = ExtractionResult.objects.select_for_update().get(id=extraction_id)
            if job.status not in {"QUEUED", "PROCESSING"} or job.updated_at >= cutoff:
                continue
            job.status = "FAILED"
            job.claim_token = None
            job.output = {"warnings": ["Extraction stopped responding. The job has been released; retry extraction to continue."], "error_code": "WORKER_STALLED"}
            job.save(update_fields=["status", "claim_token", "output", "updated_at"])
            latest = invoice.extractions.order_by("-created_at").values_list("id", flat=True).first()
            if latest == job.id and invoice.status == Invoice.Status.EXTRACTING:
                invoice.status = Invoice.Status.EXTRACTION_FAILED
                invoice.save(update_fields=["status", "updated_at"])
            AuditLog.objects.create(tenant=invoice.tenant, action="EXTRACTION_STALLED_RECOVERED", object_type="Invoice", object_id=str(invoice.id), metadata={"extraction_id": str(job.id)})
            recovered += 1
    return recovered
