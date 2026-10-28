"""Durable invoice progression. Never creates suppliers, bank transfers or payment records."""
import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from uuid import uuid4
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from accounts.models import Membership
from admin_console.services import has_feature
from audit.models import AuditLog
from invoices.models import Invoice
from notifications.models import Notification

logger = logging.getLogger(__name__)
EDITABLE = {Invoice.Status.REVIEW_REQUIRED, Invoice.Status.EXCEPTION, Invoice.Status.MATCHED}


def _state(invoice, status, message, **extra):
    invoice.automation = {**invoice.automation, "status": status, "message": message, "updated_at": timezone.now().isoformat(), **extra}
    invoice.save(update_fields=["automation", "updated_at"])
    AuditLog.objects.create(tenant=invoice.tenant, action="INVOICE_AUTOMATION_"+status, object_type="Invoice", object_id=str(invoice.pk), metadata={"message": message, "version": invoice.version, "run_id": invoice.automation.get("run_id")})
    if status in {"NEEDS_ATTENTION", "FAILED", "PAYMENT_READY"}:
        notification_roles = extra.get("notification_roles", ["OWNER", "FINANCE"])
        members = Membership.objects.filter(tenant=invoice.tenant, is_active=True, user__is_active=True, role__in=notification_roles).select_related("user")
        for member in members:
            if status == "PAYMENT_READY":
                payload = {"title": "Invoice ready for payment", "body": message, "link": "/payments", "invoice_id": str(invoice.pk), "version": invoice.version, "category": "payments"}
            else:
                payload = {"title": "Invoice needs attention", "body": message, "link": "/exceptions" if extra.get("notification_roles") else "/invoices", "invoice_id": str(invoice.pk), "version": invoice.version, "category": "invoices"}
            Notification.objects.get_or_create(tenant=invoice.tenant, recipient=member.user, channel="IN_APP", payload=payload, defaults={"status": "UNREAD"})
    return invoice.automation


def _dispatch(invoice_id, run_id):
    try:
        from invoices.tasks import advance_invoice
        advance_invoice.delay(str(invoice_id), run_id)
    except Exception:
        # State is already committed. Beat republishes queued work after recovery.
        logger.warning("Invoice workflow queued in database; waiting for broker recovery.")


@transaction.atomic
def queue_invoice_workflow(invoice, actor=None, reviewed=False):
    locked = Invoice.objects.select_for_update(of=("self",)).select_related("tenant").get(pk=invoice.pk, tenant_id=invoice.tenant_id)
    if locked.status not in EDITABLE or locked.financial_locked_at or locked.payment_status != "UNPAID":
        return locked.automation
    if locked.tenant.settings.get("automatic_invoice_workflow_enabled", True) is not True:
        return _state(locked, "PAUSED", "Automatic workflow is disabled for this company.")
    prior = locked.automation or {}
    if prior.get("status") in {"QUEUED", "RUNNING", "RETRY"} and prior.get("version") == locked.version:
        return prior
    run_id = str(uuid4())
    locked.automation = {"run_id": run_id, "version": locked.version, "reviewed": reviewed, "actor_id": str(actor.pk) if actor else None, "attempts": 0}
    _state(locked, "QUEUED", "Queued for supplier validation, matching and approval routing.", next_attempt_at=timezone.now().isoformat())
    transaction.on_commit(lambda: _dispatch(locked.pk, run_id))
    return locked.automation


def _number(value):
    try:
        number = Decimal(str(value))
        return number if number.is_finite() else None
    except (InvalidOperation, ValueError, TypeError):
        return None


@transaction.atomic
def advance_workflow(invoice_id, run_id):
    invoice = Invoice.objects.select_for_update(of=("self",)).select_related("tenant", "vendor").get(pk=invoice_id)
    state = invoice.automation or {}
    if state.get("run_id") != run_id or state.get("version") != invoice.version or state.get("status") != "RUNNING":
        return {"status": "STALE_IGNORED"}
    if invoice.status not in EDITABLE or invoice.financial_locked_at or invoice.payment_status != "UNPAID" or invoice.payment_allocations.exists():
        return _state(invoice, "STOPPED", "Invoice has moved to another financial stage; automatic processing stopped.")
    tenant = invoice.tenant
    if tenant.is_deleted or tenant.settings.get("automatic_invoice_workflow_enabled", True) is not True:
        return _state(invoice, "PAUSED", "Automatic workflow is disabled for this company.")
    subscription = tenant.admin_subscriptions.order_by("-created_at").first()
    if not subscription or subscription.status not in {"ACTIVE", "TRIAL", "GRACE_PERIOD"} or (subscription.status == "TRIAL" and subscription.trial_ends_at and subscription.trial_ends_at <= timezone.now()):
        return _state(invoice, "NEEDS_ATTENTION", "Company billing or access must be restored before automatic processing.")
    if not all(has_feature(tenant, key) for key in ["invoice_upload", "po_grn_matching", "approval_workflow"]):
        return _state(invoice, "NEEDS_ATTENTION", "Invoice upload, matching and approval features must be enabled for this company.")
    reviewed = state.get("reviewed") is True
    latest = invoice.extractions.order_by("-created_at", "-id").first()
    if not reviewed:
        if not has_feature(tenant, "ai_extraction"):
            return _state(invoice, "NEEDS_ATTENTION", "Automatic extraction access is disabled. A person must review the invoice.")
        confidence = latest.confidence if latest and latest.status == "COMPLETED" and isinstance(latest.confidence, dict) else {}
        threshold = Decimal(str(settings.INVOICE_AUTO_MATCH_CONFIDENCE_THRESHOLD))
        uncertain = [field for field in ["supplier_name", "invoice_number", "invoice_date", "invoice_total"] if _number(confidence.get(field)) is None or not threshold <= _number(confidence.get(field)) <= 1]
        if uncertain:
            return _state(invoice, "NEEDS_ATTENTION", "Review uncertain extracted fields: " + ", ".join(field.replace("_", " ") for field in uncertain)+".")
    if not invoice.invoice_number or not invoice.invoice_date or invoice.invoice_date > timezone.localdate() or invoice.invoice_total <= 0:
        return _state(invoice, "NEEDS_ATTENTION", "Check the invoice number, date and positive total before continuing.")
    lines = list(invoice.lines.all())
    if not lines or any(line.quantity <= 0 or line.rate < 0 or line.taxable_value < 0 or line.gst_amount < 0 or line.tds_amount < 0 for line in lines):
        return _state(invoice, "NEEDS_ATTENTION", "Review missing or invalid invoice line items.")
    line_total = sum((line.taxable_value+line.gst_amount-line.tds_amount for line in lines), Decimal("0"))
    if abs(line_total-invoice.invoice_total) > Decimal("0.02") or any(abs(line.quantity*line.rate-line.taxable_value)>Decimal("0.02") or abs(line.taxable_value*line.gst_rate/100-line.gst_amount)>Decimal("0.02") for line in lines):
        return _state(invoice, "NEEDS_ATTENTION", "Invoice totals or tax calculations differ from the line items. Review discounts, rounding and taxes.")
    if not invoice.vendor_id or not reviewed and invoice.vendor_match_method != "MANUAL_REVIEW":
        candidates = list(tenant.vendor_set.filter(gstin__iexact=invoice.supplier_gstin.strip())[:2]) if invoice.supplier_gstin.strip() else []
        if len(candidates) != 1 or (invoice.vendor_id and candidates[0].pk != invoice.vendor_id):
            return _state(invoice, "NEEDS_ATTENTION", "Select the correct supplier: GSTIN is missing, ambiguous or conflicts with the linked supplier.", recheck_after=(timezone.now()+timedelta(minutes=5)).isoformat() if invoice.supplier_gstin else None)
        vendor = candidates[0]
        if not invoice.vendor_id:
            invoice.vendor = vendor
            invoice.vendor_match_method = "GSTIN"
            invoice.vendor_match_confidence = Decimal("1")
            invoice.save(update_fields=["vendor", "vendor_match_method", "vendor_match_confidence", "updated_at"])
            AuditLog.objects.create(tenant=tenant, action="SUPPLIER_AUTO_LINKED", object_type="Invoice", object_id=str(invoice.pk), metadata={"vendor_id": str(vendor.pk), "method": "UNIQUE_GSTIN", "version": invoice.version})
    if not invoice.vendor or invoice.vendor.tenant_id != tenant.pk or not invoice.vendor.approved:
        return _state(invoice, "NEEDS_ATTENTION", "The supplier must belong to this company and be approved.", recheck_after=(timezone.now()+timedelta(minutes=5)).isoformat())
    if Invoice.objects.filter(tenant=tenant, vendor_id=invoice.vendor_id).exclude(pk=invoice.pk).count() > 500:
        return _state(invoice, "NEEDS_ATTENTION", "Supplier history exceeds the automatic duplicate-search limit. Complete a manual duplicate review and approval.")
    from matching.services import run_matching
    from approvals.workflow import submit_for_approval
    from rest_framework.exceptions import ValidationError
    # Separate savepoint: a business exception rolls back partial approval writes only.
    run_matching(invoice)
    if invoice.status != Invoice.Status.MATCHED:
        codes = list(invoice.exceptions.filter(status__in=["OPEN", "ASSIGNED"]).values_list("code", flat=True).distinct())
        labels = [code.replace("_", " ").title() for code in codes]
        roles = {"OWNER", "FINANCE"}
        if set(codes) & {"MISSING_PO", "QTY_OVER_INVOICE", "RATE_VARIANCE"}: roles.add("PURCHASE")
        if set(codes) & {"MISSING_GRN", "PARTIAL_DELIVERY", "SERVICE_NOT_ACCEPTED"}: roles.update({"PURCHASE", "STORE"})
        reason = ", ".join(labels) if labels else "Invoice matching needs review"
        return _state(invoice, "NEEDS_ATTENTION", f"Matching needs attention: {reason}. Review the exception details; supporting records are checked again in five minutes.", recheck_after=(timezone.now()+timedelta(minutes=5)).isoformat(), notification_roles=sorted(roles))
    try:
        with transaction.atomic():
            result = submit_for_approval(invoice)
    except ValidationError as error:
        details = error.detail
        message = str(details.get("detail", details)) if isinstance(details, dict) else str(details)
        return _state(invoice, "NEEDS_ATTENTION", message, recheck_after=(timezone.now()+timedelta(minutes=5)).isoformat())
    invoice.status = result.status
    invoice.financial_locked_at = result.financial_locked_at
    if result.status == Invoice.Status.PAYMENT_READY:
        return _state(invoice, "PAYMENT_READY", "Matched and approved under a configured policy. Ready for payment recording; no money has been transferred.")
    return _state(invoice, "AWAITING_APPROVAL", "Matching is complete. The assigned approver has been notified; no further submission click is needed.")
