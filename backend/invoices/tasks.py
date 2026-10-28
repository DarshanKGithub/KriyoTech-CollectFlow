import uuid
from celery import shared_task
from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail
from django.utils.dateparse import parse_date
from django.db import transaction
from invoices.models import Invoice, InvoiceLine, ExtractionResult
from vendors.services import get_extraction_provider, TransientExtractionError
from audit.models import AuditLog
from accounts.models import Membership
from notifications.models import Notification, NotificationPreference


@shared_task
def maintain_extraction_queue():
    import redis
    from invoices.extraction import recover_stalled_extractions
    recovered = recover_stalled_extractions()
    client = redis.Redis.from_url(settings.CELERY_BROKER_URL, socket_connect_timeout=3, socket_timeout=3)
    client.set("kriyopay:extraction-worker-heartbeat", timezone.now().isoformat(), ex=180)
    return {"recovered": recovered}

def _confidence_at_least(value, threshold):
    try:
        return float(value) >= threshold
    except (TypeError, ValueError):
        return False

@shared_task(bind=True, max_retries=3, acks_late=True, reject_on_worker_lost=True)
def extract_invoice(self, invoice_id, extraction_id=None):
    # Claim under the invoice lock so duplicate deliveries never run together.
    with transaction.atomic():
        invoice = Invoice.objects.select_for_update(of=("self",)).select_related("document").get(id=invoice_id)
        if not invoice.document_id:
            return {"status": "MANUAL_ENTRY"}
        if extraction_id:
            extraction = ExtractionResult.objects.select_for_update().filter(id=extraction_id, invoice=invoice).first()
            if not extraction:
                return {"status": "IGNORED"}
        else:
            extraction = invoice.extractions.order_by("-created_at").first()
            if not extraction:
                extraction = ExtractionResult.objects.create(tenant=invoice.tenant, invoice=invoice, status="QUEUED", provider=settings.EXTRACTION_PROVIDER)
        if extraction.status != "QUEUED":
            return {"status": extraction.status, "duplicate_delivery": True}
        latest = invoice.extractions.order_by("-created_at").values_list("id", flat=True).first()
        if latest != extraction.id or invoice.status not in {Invoice.Status.UPLOADED, Invoice.Status.EXTRACTING}:
            return {"status": "IGNORED"}
        from admin_console.services import has_feature
        if not has_feature(invoice.tenant, "ai_extraction"):
            extraction.status = "FAILED"
            extraction.output = {"warnings": ["Automatic extraction access is disabled for this company."]}
            extraction.save(update_fields=["status", "output", "updated_at"])
            invoice.status = Invoice.Status.REVIEW_REQUIRED
            invoice.save(update_fields=["status", "updated_at"])
            return {"status": "ACCESS_DISABLED"}
        claim = uuid.uuid4()
        extraction.claim_token = claim
        extraction.status = "PROCESSING"
        extraction.attempts += 1
        extraction.save(update_fields=["claim_token", "status", "attempts", "updated_at"])
        invoice.status = Invoice.Status.EXTRACTING
        invoice.save(update_fields=["status", "updated_at"])
    try:
        if invoice.document.tenant_id != invoice.tenant_id:
            raise RuntimeError("Source document does not belong to the invoice workspace.")
        output = get_extraction_provider().extract(invoice.document)
        with transaction.atomic():
            invoice = Invoice.objects.select_for_update().get(id=invoice_id)
            extraction = ExtractionResult.objects.select_for_update().get(id=extraction.id)
            if extraction.status != "PROCESSING" or extraction.claim_token != claim or invoice.status != Invoice.Status.EXTRACTING:
                return {"status": "STALE_RESULT_IGNORED"}
            fields = output.get("fields", {})
            for field in ("supplier_name", "supplier_gstin", "invoice_number", "po_number"):
                if field in fields: setattr(invoice, field, fields[field] or "")
            for field in ("invoice_date", "due_date"):
                if field in fields: setattr(invoice, field, parse_date(fields[field]) if fields[field] else None)
            for field in ("taxable_total", "gst_total", "tds_total", "invoice_total"):
                if field in fields: setattr(invoice, field, fields[field] or 0)
            invoice.save()
            extracted_lines = output.get("lines", [])
            if extracted_lines:
                invoice.lines.all().delete()
                allowed_line_fields = {"item_code", "description", "hsn_sac", "quantity", "uom", "rate", "taxable_value", "gst_rate", "gst_amount", "tds_amount"}
                for line_no, line in enumerate(extracted_lines, 1):
                    InvoiceLine.objects.create(tenant=invoice.tenant, invoice=invoice, line_no=line_no, **{key: value for key, value in line.items() if key in allowed_line_fields})
            if extraction:
                extraction.provider = settings.EXTRACTION_PROVIDER
                extraction.output = output
                extraction.confidence = output.get("confidence", {})
                extraction.status = "COMPLETED"
                extraction.claim_token = None
                extraction.save(update_fields=["provider", "output", "confidence", "status", "claim_token", "updated_at"])
            else:
                ExtractionResult.objects.create(tenant=invoice.tenant, invoice=invoice, provider=settings.EXTRACTION_PROVIDER, output=output, confidence=output.get("confidence", {}), status="COMPLETED")
            invoice.status = Invoice.Status.REVIEW_REQUIRED
            invoice.save(update_fields=["status", "updated_at"])
            from invoices.automation import queue_invoice_workflow
            queue_invoice_workflow(invoice)
            AuditLog.objects.create(tenant=invoice.tenant, actor=invoice.uploaded_by, action="EXTRACTION_COMPLETED", object_type="Invoice", object_id=str(invoice.id), metadata={"provider": settings.EXTRACTION_PROVIDER, "workflow_queued": True})
        return {"status": "COMPLETED", "invoice_id": str(invoice.id)}
    except Exception as error:
        retry = False
        with transaction.atomic():
            invoice = Invoice.objects.select_for_update().get(id=invoice_id)
            extraction = ExtractionResult.objects.select_for_update().get(id=extraction.id)
            if extraction.claim_token != claim or extraction.status != "PROCESSING" or invoice.status != Invoice.Status.EXTRACTING:
                return {"status": "STALE_FAILURE_IGNORED"}
            retry = isinstance(error, (TransientExtractionError, TimeoutError)) and extraction.attempts < 4
            warning = "Extraction provider is temporarily unavailable. Retrying automatically." if retry else "Extraction could not be completed. Retry extraction or review the invoice manually."
            extraction.status = "QUEUED" if retry else "FAILED"
            extraction.claim_token = None
            extraction.output = {"warnings": [warning], "error_code": "PROVIDER_TEMPORARY" if retry else "EXTRACTION_FAILED", "attempts": extraction.attempts}
            extraction.save(update_fields=["status", "claim_token", "output", "updated_at"])
            invoice.status = Invoice.Status.EXTRACTING if retry else Invoice.Status.EXTRACTION_FAILED
            invoice.save(update_fields=["status", "updated_at"])
            if retry:
                AuditLog.objects.create(tenant=invoice.tenant, actor=invoice.uploaded_by, action="EXTRACTION_RETRY_SCHEDULED", object_type="Invoice", object_id=str(invoice.id), metadata={"attempt": extraction.attempts})
        if retry:
            raise self.retry(exc=TransientExtractionError("Temporary extraction failure"), countdown=min(30 * (2 ** (extraction.attempts - 1)), 120), args=(str(invoice.id), str(extraction.id)))
        AuditLog.objects.create(
            tenant=invoice.tenant,
            actor=invoice.uploaded_by,
            action="EXTRACTION_FAILED",
            object_type="Invoice",
            object_id=str(invoice.id),
            metadata={"extraction_id": str(extraction.id) if extraction else None, "retryable": True},
        )
        controls = invoice.tenant.settings.get("fleet_controls", {})
        recipient_roles = controls.get("recipient_roles", [Membership.Role.OWNER, Membership.Role.FINANCE, Membership.Role.PURCHASE])
        channels = controls.get("channels", ["IN_APP"])
        for member in Membership.objects.filter(tenant=invoice.tenant, is_active=True, role__in=recipient_roles).select_related("user"):
            preference = NotificationPreference.objects.filter(tenant=invoice.tenant, user=member.user).first()
            if preference and not preference.preferences.get("invoices", True):
                continue
            duplicate = Notification.objects.filter(tenant=invoice.tenant, recipient=member.user, payload__invoice_id=str(invoice.id), payload__category="invoices").exists()
            if duplicate:
                continue
            for channel in channels:
                notification = Notification.objects.create(tenant=invoice.tenant, recipient=member.user, channel=channel,
                    status="UNREAD" if channel == "IN_APP" else "PENDING",
                    payload={"title": "Invoice extraction failed", "body": f"Invoice {invoice.invoice_number or invoice.id} could not be extracted. Review the invoice and retry extraction.", "link": "/invoices", "category": "invoices", "invoice_id": str(invoice.id)})
                if channel == "EMAIL":
                    sent = send_mail("Invoice extraction failed", f"Invoice {invoice.invoice_number or invoice.id} in {invoice.tenant.name} could not be extracted. Review and retry in KriyoPay.", settings.DEFAULT_FROM_EMAIL, [member.user.email], fail_silently=True)
                    if sent:
                        notification.status = "SENT"
                        notification.save(update_fields=["status"])
        raise

@shared_task(bind=True, max_retries=3, acks_late=True, reject_on_worker_lost=True)
def advance_invoice(self, invoice_id, run_id):
    from datetime import timedelta
    from invoices.automation import advance_workflow, _state
    with transaction.atomic():
        invoice = Invoice.objects.select_for_update().filter(pk=invoice_id).first()
        if not invoice:
            return {"status": "REMOVED"}
        state = invoice.automation or {}
        if state.get("run_id") != run_id or state.get("version") != invoice.version or state.get("status") not in {"QUEUED", "RETRY"}:
            return {"status": "STALE_IGNORED"}
        attempts = int(state.get("attempts", 0)) + 1
        _state(invoice, "RUNNING", "Validating supplier, totals and matching records.", attempts=attempts)
    try:
        return advance_workflow(invoice_id, run_id)
    except Exception:
        with transaction.atomic():
            invoice = Invoice.objects.select_for_update().get(pk=invoice_id)
            if invoice.automation.get("run_id") != run_id or invoice.automation.get("version") != invoice.version:
                return {"status": "STALE_IGNORED"}
            if attempts >= 4:
                return _state(invoice, "FAILED", "Automatic processing could not finish. Review the invoice or retry automation.")
            delay = min(30*(2**(attempts-1)), 120)
            _state(invoice, "RETRY", "Temporary processing failure; retrying automatically.", next_attempt_at=(timezone.now()+timedelta(seconds=delay)).isoformat())
        raise self.retry(countdown=delay, args=(invoice_id, run_id))


@shared_task
def maintain_invoice_workflows():
    from datetime import timedelta
    from django.utils.dateparse import parse_datetime
    from invoices.automation import _dispatch, _state, queue_invoice_workflow
    # Recheck only resumable dependency waits, never uncertain extraction fields.
    waiting = Invoice.objects.filter(automation__status="NEEDS_ATTENTION", automation__recheck_after__lte=timezone.now().isoformat(), status__in=["REVIEW_REQUIRED", "EXCEPTION", "MATCHED"]).order_by("updated_at")[:100]
    for invoice in waiting:
        queue_invoice_workflow(invoice, reviewed=invoice.automation.get("reviewed") is True and invoice.automation.get("version") == invoice.version)
    cutoff = timezone.now()-timedelta(minutes=5)
    pending = Invoice.objects.filter(automation__status__in=["QUEUED", "RETRY", "RUNNING"]).order_by("updated_at").values_list("id", flat=True)[:200]
    published = 0
    for invoice_id in pending:
        with transaction.atomic():
            invoice = Invoice.objects.select_for_update().get(pk=invoice_id)
            state = invoice.automation or {}
            if state.get("version") != invoice.version:
                _state(invoice, "STOPPED", "Invoice version changed; old processing request stopped.")
                continue
            if state.get("status") == "RUNNING":
                updated = parse_datetime(state.get("updated_at", ""))
                if not updated or updated > cutoff:
                    continue
                _state(invoice, "RETRY", "Recovering interrupted automatic processing.", next_attempt_at=timezone.now().isoformat())
            if invoice.automation.get("status") not in {"QUEUED", "RETRY"}:
                continue
            next_attempt = parse_datetime(invoice.automation.get("next_attempt_at", ""))
            if next_attempt and next_attempt > timezone.now():
                continue
            if int(invoice.automation.get("attempts", 0)) >= 4:
                _state(invoice, "FAILED", "Automatic processing stopped after repeated interruptions. Retry after checking the worker.")
                continue
            transaction.on_commit(lambda pk=invoice.pk, run_id=state["run_id"]: _dispatch(pk, run_id))
            published += 1
    return {"published": published}
