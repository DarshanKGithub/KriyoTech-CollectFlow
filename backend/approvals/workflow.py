"""One approval submission path for staff actions and automatic invoice processing."""
from datetime import timedelta
import logging
from django.db import transaction
from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail
from rest_framework.exceptions import ValidationError
from accounts.models import Membership, User
from admin_console.services import has_feature
from audit.models import AuditLog
from invoices.models import Invoice, CustomFieldDefinition
from approvals.models import Approval, ApprovalRule, ApprovalStep, AutoApprovalRule

logger = logging.getLogger(__name__)


def _email_approvers(subject, body, recipients):
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, recipients, fail_silently=True)
    except Exception:
        logger.warning("Approval email delivery unavailable; in-app notification retained.")


@transaction.atomic
def submit_for_approval(invoice, actor=None):
    invoice = Invoice.objects.select_for_update(of=("self",)).select_related("vendor", "tenant").get(pk=invoice.pk, tenant_id=invoice.tenant_id)
    if invoice.status in {Invoice.Status.APPROVAL_PENDING, Invoice.Status.PAYMENT_READY, Invoice.Status.EXPORTED}:
        return invoice
    if not invoice.vendor_id or invoice.vendor.tenant_id != invoice.tenant_id or not invoice.vendor.approved:
        raise ValidationError({"detail": "Link an approved supplier from this workspace before approval."})
    if invoice.status != Invoice.Status.MATCHED or not invoice.match_results.exists() or invoice.exceptions.filter(blocking=True).exclude(status__in=["RESOLVED", "OVERRIDDEN"]).exists():
        raise ValidationError({"detail": "Resolve blocking exceptions and complete matching first."})
    required = CustomFieldDefinition.objects.filter(tenant=invoice.tenant, active=True, required=True)
    filled = set(invoice.custom_field_values.filter(value__isnull=False).exclude(value="").values_list("definition__key", flat=True))
    missing = [field.name for field in required if field.key not in filled]
    if missing:
        raise ValidationError({"detail": "Complete required custom fields: " + ", ".join(missing)})
    duplicates = invoice.duplicate_checks.all()
    duplicate_clear = not duplicates.filter(decision__in=["PENDING", "CONFIRM_DUPLICATE"]).exists()
    exceptions_clear = not invoice.exceptions.exclude(status__in=["RESOLVED", "OVERRIDDEN"]).exists()
    auto_rule = None
    duplicate_scan_complete = Invoice.objects.filter(tenant=invoice.tenant, vendor_id=invoice.vendor_id).exclude(pk=invoice.pk).count() <= 500
    if has_feature(invoice.tenant, "auto_approval") and duplicate_scan_complete and duplicate_clear and exceptions_clear and (not duplicates.exists() or invoice.duplicate_review_complete):
        for rule in AutoApprovalRule.objects.filter(tenant=invoice.tenant, enabled=True).order_by("updated_at", "id"):
            # Unknown condition schemas must never silently broaden approval permission.
            if rule.conditions:
                continue
            if str(invoice.vendor_id) in [str(value) for value in rule.allowed_vendor_ids] and 0 < invoice.invoice_total <= rule.amount_limit:
                auto_rule = rule
                break
    if auto_rule:
        evaluation = {"rule_id": str(auto_rule.id), "amount_limit": str(auto_rule.amount_limit), "invoice_total": str(invoice.invoice_total), "vendor_id": str(invoice.vendor_id), "blocking_exceptions_clear": True, "duplicate_review_clear": True, "matching_completed": True, "invoice_version": invoice.version}
        Approval.objects.create(tenant=invoice.tenant, invoice=invoice, invoice_version=invoice.version, approver=None, method="AUTO_RULE", rule_evaluation=evaluation, decision="APPROVED", comments="Configured supplier and amount policy satisfied")
        invoice.status = Invoice.Status.PAYMENT_READY
        invoice.save(update_fields=["status", "updated_at"])
        AuditLog.objects.create(tenant=invoice.tenant, actor=actor, action="INVOICE_AUTO_APPROVED", object_type="Invoice", object_id=str(invoice.id), metadata=evaluation)
        return invoice
    from invoices.phase2_extended import rule_matches, notify
    approval_rule = next((rule for rule in ApprovalRule.objects.filter(tenant=invoice.tenant, active=True).order_by("priority", "id") if rule_matches(rule, invoice)), None)
    steps = approval_rule.steps if approval_rule else []
    configs = []
    for config in steps:
        approver_id, role = config.get("user_id"), config.get("role", "")
        approver = User.objects.filter(pk=approver_id, is_active=True, memberships__tenant=invoice.tenant, memberships__is_active=True).first() if approver_id else None
        if approver_id and (not approver or approver.pk == invoice.uploaded_by_id):
            raise ValidationError({"detail": "Approval rule must assign an active approver other than the invoice submitter."})
        if not approver_id and (role not in {"OWNER", "FINANCE", "APPROVER"} or not Membership.objects.filter(tenant=invoice.tenant, is_active=True, role=role, user__is_active=True).exclude(user_id=invoice.uploaded_by_id).exists()):
            raise ValidationError({"detail": "Configure an eligible approver other than the invoice submitter."})
        configs.append((config, approver, role))
    eligible = Membership.objects.filter(tenant=invoice.tenant, is_active=True, user__is_active=True, role__in=["OWNER", "FINANCE", "APPROVER"]).exclude(user_id=invoice.uploaded_by_id)
    if not configs and not eligible.exists():
        raise ValidationError({"detail": "Invite another approver or configure an explicit auto-approval rule for this supplier and amount."})
    invoice.status = Invoice.Status.APPROVAL_PENDING
    invoice.save(update_fields=["status", "updated_at"])
    workflow_version = (invoice.approval_steps.order_by("-workflow_version").values_list("workflow_version", flat=True).first() or 0) + 1
    for sequence, (config, approver, role) in enumerate(configs, 1):
        due_hours = min(max(int(config.get("due_hours", 72)), 1), 8760)
        ApprovalStep.objects.create(tenant=invoice.tenant, invoice=invoice, workflow_version=workflow_version, sequence=sequence, approver_role=role, approver=approver, due_at=timezone.now()+timedelta(hours=due_hours), evaluation={"rule_id": str(approval_rule.id), "rule_name": approval_rule.name, "invoice_version": invoice.version})
    if configs:
        _, first_user, first_role = configs[0]
        eligible = eligible.filter(user=first_user) if first_user else eligible.filter(role=first_role)
    from notifications.models import NotificationPreference
    emails = []
    for member in eligible.select_related("user").distinct():
        notify(invoice.tenant, member.user, "Approval required", f"Invoice {invoice.invoice_number or invoice.id} is ready for your decision.", "/approvals")
        pref = NotificationPreference.objects.filter(tenant=invoice.tenant, user=member.user).first()
        if not pref or pref.preferences.get("email", True):
            emails.append(member.user.email)
    AuditLog.objects.create(tenant=invoice.tenant, actor=actor, action="APPROVAL_SUBMITTED", object_type="Invoice", object_id=str(invoice.id), metadata={"version": invoice.version, "rule_id": str(approval_rule.id) if approval_rule else None})
    if emails:
        transaction.on_commit(lambda: _email_approvers("Invoice approval required", f"Invoice {invoice.invoice_number} in {invoice.tenant.name} is awaiting approval. Sign in to review version {invoice.version}.", emails))
    return invoice
