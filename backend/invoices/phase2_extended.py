import hashlib
import secrets
from datetime import date, timedelta
from decimal import Decimal
import csv
import io

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.text import slugify
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.http import HttpResponse
from rest_framework.views import APIView

from accounts.models import Membership, User
from accounts.permissions import HasTenantMembership
from approvals.models import Approval, ApprovalDelegation, ApprovalRule, ApprovalStep, AutoApprovalRule
from audit.models import AuditLog
from documents.models import Document
from exceptions_app.models import ExceptionEscalation, ExceptionSLA, InvoiceException
from inbound_email.models import EmailIngestionLog
from invoices.models import CustomFieldDefinition, DuplicateCheck, Invoice, InvoiceCustomFieldValue, VendorFollowUpDraft
from notifications.models import Notification, NotificationPreference
from operations.models import BulkJob
from payments.models import PaymentAllocation, CreditDebitNote
from payments.services import with_invoice_balances
from procurement.models import GRN
from tenants.models import Tenant


FINANCE = {"OWNER", "FINANCE"}


def err(code, message, status=400):
    return Response({"error": {"code": code, "message": message}}, status=status)


def notify(tenant, user, title, body, link=""):
    pref = NotificationPreference.objects.filter(tenant=tenant, user=user).first()
    if pref and not pref.preferences.get("exceptions", True) and "exception" in title.lower(): return
    if pref and not pref.preferences.get("approvals", True) and "approval" in title.lower(): return
    Notification.objects.create(tenant=tenant, recipient=user, channel="IN_APP", status="UNREAD",
                                payload={"title": title, "body": body, "link": link})


class IntakeToken(APIView):
    permission_classes = [HasTenantMembership]

    def get(self, request):
        if request.membership.role not in FINANCE:
            return err("PERMISSION_DENIED", "Owner or finance role required", 403)
        if not request.tenant.invoice_intake_token:
            request.tenant.invoice_intake_token = secrets.token_urlsafe(32)
            request.tenant.save(update_fields=["invoice_intake_token"])
        return Response({"workspace_key": request.tenant.workspace_key, "token": request.tenant.invoice_intake_token,
                         "webhook_path": f"/api/v1/email-ingestion/{request.tenant.workspace_key}"})

    def post(self, request):
        if request.membership.role not in FINANCE:
            return err("PERMISSION_DENIED", "Owner or finance role required", 403)
        request.tenant.invoice_intake_token = secrets.token_urlsafe(32)
        request.tenant.save(update_fields=["invoice_intake_token"])
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="INVOICE_INTAKE_TOKEN_ROTATED",
                                object_type="Tenant", object_id=str(request.tenant.id), metadata={})
        return Response({"token": request.tenant.invoice_intake_token})


class EmailIngestionWebhook(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request, workspace_key):
        tenant = Tenant.objects.filter(workspace_key=workspace_key).first()
        supplied = request.headers.get("X-Invoice-Intake-Token", "")
        if not tenant or not tenant.invoice_intake_token or not secrets.compare_digest(supplied, tenant.invoice_intake_token):
            return err("AUTHENTICATION_REQUIRED", "Invalid intake token", 401)
        from admin_console.services import has_feature
        if tenant.admin_subscriptions.exists() and not has_feature(tenant, "email_invoice_intake"):
            return err("FEATURE_NOT_AVAILABLE", "Email invoice intake is not enabled for this plan", 403)
        message_id = str(request.data.get("message_id", "")).strip()
        provider = str(request.data.get("provider", "WEBHOOK")).strip().upper()[:40]
        if not message_id:
            return err("VALIDATION_ERROR", "message_id is required for idempotent ingestion")
        log, created = EmailIngestionLog.objects.get_or_create(tenant=tenant, provider=provider, message_id=message_id,
            defaults={"sender": request.data.get("sender", ""), "recipient": request.data.get("recipient", ""), "subject": request.data.get("subject", ""), "status": EmailIngestionLog.Status.PROCESSING})
        if not created and log.status in (EmailIngestionLog.Status.PROCESSED, EmailIngestionLog.Status.PARTIAL):
            return Response({"id": str(log.id), "status": log.status, "duplicate_delivery": True, "attachments": log.attachment_results})
        if not created and log.status == EmailIngestionLog.Status.PROCESSING:
            return Response({"id": str(log.id), "status": log.status, "duplicate_delivery": True}, status=202)
        if not created:
            log.retry_count += 1
            log.status = EmailIngestionLog.Status.PROCESSING
            log.error = ""
            log.save(update_fields=["retry_count", "status", "error"])
        attachments = request.FILES.getlist("attachments") or request.FILES.getlist("file")
        if len(attachments) > 20 or sum(f.size for f in attachments) > 100 * 1024 * 1024:
            log.status = EmailIngestionLog.Status.QUARANTINED; log.error = "Email exceeds the attachment count or total size limit"; log.processed_at = timezone.now()
            log.save(update_fields=["status", "error", "processed_at"])
            return err("VALIDATION_ERROR", log.error, 413)
        if not attachments:
            log.status = EmailIngestionLog.Status.PARTIAL
            log.error = "Email received without invoice attachments"
            log.processed_at = timezone.now()
            log.save(update_fields=["status", "error", "processed_at"])
            return Response({"id": str(log.id), "status": log.status, "attachments": []}, status=202)
        results = []
        for uploaded in attachments:
            prior = next((r for r in log.attachment_results if r.get("filename") == uploaded.name and r.get("status") != "QUARANTINED"), None)
            if prior:
                results.append(prior)
                continue
            if uploaded.size > 25 * 1024 * 1024 or uploaded.content_type not in {"application/pdf", "image/jpeg", "image/png", "image/heic", "image/heif"}:
                results.append({"filename": uploaded.name, "status": "QUARANTINED", "reason": "Unsupported type or file exceeds 25 MB"})
                continue
            digest = hashlib.sha256(uploaded.read()).hexdigest()
            uploaded.seek(0)
            with transaction.atomic():
                candidate_doc = Document.objects.filter(tenant=tenant, checksum_sha256=digest).first()
                candidate = Invoice.objects.filter(tenant=tenant, document=candidate_doc).first() if candidate_doc else None
                document = Document.objects.create(tenant=tenant, filename=uploaded.name, media_type=uploaded.content_type,
                    checksum_sha256=digest, size_bytes=uploaded.size, file=uploaded)
                invoice = Invoice.objects.create(tenant=tenant, document=document, status=Invoice.Status.REVIEW_REQUIRED,
                    source_email={"message_id": message_id, "sender": log.sender, "subject": log.subject})
                AuditLog.objects.create(tenant=tenant, actor=None, action="INVOICE_RECEIVED_BY_EMAIL", object_type="Invoice", object_id=str(invoice.id), metadata={"message_id": message_id, "checksum": digest, "filename": uploaded.name})
                if candidate:
                    DuplicateCheck.objects.create(tenant=tenant, invoice=invoice, candidate_invoice=candidate, kind=DuplicateCheck.Kind.FILE,
                        score=1, reasons=["Identical SHA-256 document checksum from inbound email"])
                    InvoiceException.objects.create(tenant=tenant, invoice=invoice, code="DUPLICATE_INVOICE", details={"candidate_invoice_id": str(candidate.id)})
                    invoice.status = Invoice.Status.EXCEPTION
                    invoice.save(update_fields=["status", "updated_at"])
                    for member in Membership.objects.filter(tenant=tenant, is_active=True, user__is_active=True, role__in=FINANCE).select_related("user"):
                        Notification.objects.get_or_create(tenant=tenant, recipient=member.user, channel="IN_APP",
                            payload={"title": "Duplicate invoice needs review", "body": "An email attachment matches a previously received invoice. Review the duplicate before proceeding.", "link": "/invoices", "invoice_id": str(invoice.id), "category": "invoices"},
                            defaults={"status": "UNREAD"})
                else:
                    from .extraction import queue_invoice_extraction
                    queue_invoice_extraction(invoice)
                result = {"filename": uploaded.name, "checksum": digest, "invoice_id": str(invoice.id), "status": invoice.status}
                results.append(result)
                log.attachment_results = results
                log.save(update_fields=["attachment_results"])
        log.attachment_results = results
        log.status = EmailIngestionLog.Status.PROCESSED if results and all(x["status"] != "QUARANTINED" for x in results) else EmailIngestionLog.Status.PARTIAL
        log.processed_at = timezone.now()
        log.save(update_fields=["attachment_results", "status", "processed_at"])
        return Response({"id": str(log.id), "status": log.status, "attachments": results}, status=202)


class EmailLogs(APIView):
    permission_classes = [HasTenantMembership]
    def get(self, request):
        if request.membership.role not in FINANCE: return err("PERMISSION_DENIED", "Finance role required", 403)
        rows = EmailIngestionLog.objects.filter(tenant=request.tenant).order_by("-created_at")[:200]
        return Response([{"id": str(x.id), "provider": x.provider, "message_id": x.message_id, "sender": x.sender, "subject": x.subject,
            "status": x.status, "error": x.error, "attachments": x.attachment_results, "created_at": x.created_at} for x in rows])


class ApprovalRules(APIView):
    permission_classes = [HasTenantMembership]

    def get(self, request):
        rows = ApprovalRule.objects.filter(tenant=request.tenant).order_by("priority", "created_at")
        return Response([{"id": str(x.id), "name": x.name, "priority": x.priority, "conditions": x.conditions, "steps": x.steps, "active": x.active} for x in rows])

    def post(self, request):
        if request.membership.role not in FINANCE: return err("PERMISSION_DENIED", "Finance role required", 403)
        name, steps, conditions = str(request.data.get("name", "")).strip(), request.data.get("steps"), request.data.get("conditions", {})
        if not name or not isinstance(steps, list) or not steps or not isinstance(conditions, dict): return err("VALIDATION_ERROR", "name, conditions, and at least one approval step are required")
        for step in steps:
            if not isinstance(step, dict): return err("VALIDATION_ERROR", "Approval steps must be objects")
            role = step.get("role", "")
            if role and role not in {"OWNER", "FINANCE", "APPROVER"}: return err("VALIDATION_ERROR", "Approval steps must use OWNER, FINANCE, or APPROVER roles")
            if not role and not step.get("user_id"): return err("VALIDATION_ERROR", "Each approval step must select a role or user")
            if step.get("user_id") and not Membership.objects.filter(tenant=request.tenant, user_id=step["user_id"], is_active=True).exists(): return err("VALIDATION_ERROR", "Approval user must be an active workspace member")
            try: due_hours = int(step.get("due_hours", 72))
            except (TypeError, ValueError): return err("VALIDATION_ERROR", "due_hours must be between 1 and 8760")
            if due_hours < 1 or due_hours > 8760: return err("VALIDATION_ERROR", "due_hours must be between 1 and 8760")
        try:
            if int(request.data.get("priority", 100)) < 0: return err("VALIDATION_ERROR", "priority must be non-negative")
        except (TypeError, ValueError): return err("VALIDATION_ERROR", "priority must be an integer")
        if "categories" in conditions and not isinstance(conditions["categories"], list): return err("VALIDATION_ERROR", "categories must be a list")
        if "vendor_ids" in conditions:
            from vendors.models import Vendor
            if not isinstance(conditions["vendor_ids"], list) or any(not Vendor.objects.filter(tenant=request.tenant, id=x).exists() for x in conditions["vendor_ids"]): return err("VALIDATION_ERROR", "Rule vendors must belong to this workspace")
        try:
            if "min_amount" in conditions and Decimal(str(conditions["min_amount"])) < 0: raise ValueError()
            if "max_amount" in conditions and Decimal(str(conditions["max_amount"])) < 0: raise ValueError()
        except Exception: return err("VALIDATION_ERROR", "Approval amounts must be non-negative numbers")
        row = ApprovalRule.objects.create(tenant=request.tenant, name=name, priority=int(request.data.get("priority", 100)), conditions=conditions,
            steps=steps, active=bool(request.data.get("active", True)), created_by=request.user, updated_by=request.user)
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="APPROVAL_RULE_CREATED", object_type="ApprovalRule", object_id=str(row.id), metadata={"name": row.name})
        return Response({"id": str(row.id), "name": row.name, "priority": row.priority, "conditions": row.conditions, "steps": row.steps, "active": row.active}, status=201)

    def patch(self, request, rule_id=None):
        if request.membership.role not in FINANCE: return err("PERMISSION_DENIED", "Finance role required", 403)
        rule = get_object_or_404(ApprovalRule, tenant=request.tenant, id=rule_id)
        proposed_steps = request.data.get("steps", rule.steps)
        if not isinstance(proposed_steps, list) or not proposed_steps: return err("VALIDATION_ERROR", "Rule needs at least one approval step")
        for step in proposed_steps:
            if not isinstance(step, dict): return err("VALIDATION_ERROR", "Approval steps must be objects")
            if step.get("role") and step["role"] not in {"OWNER", "FINANCE", "APPROVER"}: return err("VALIDATION_ERROR", "Invalid approval role")
            if step.get("user_id") and not Membership.objects.filter(tenant=request.tenant, user_id=step["user_id"], is_active=True).exists(): return err("VALIDATION_ERROR", "Approval user must be active in this workspace")
            if not step.get("role") and not step.get("user_id"): return err("VALIDATION_ERROR", "Each step must select a user or role")
            try: due_hours = int(step.get("due_hours", 72))
            except (TypeError, ValueError): return err("VALIDATION_ERROR", "due_hours must be between 1 and 8760")
            if due_hours < 1 or due_hours > 8760: return err("VALIDATION_ERROR", "due_hours must be between 1 and 8760")
        conditions = request.data.get("conditions", rule.conditions)
        if not isinstance(conditions, dict): return err("VALIDATION_ERROR", "conditions must be an object")
        if "categories" in conditions and not isinstance(conditions["categories"], list): return err("VALIDATION_ERROR", "categories must be a list")
        if "priority" in request.data:
            try:
                if int(request.data["priority"]) < 0: return err("VALIDATION_ERROR", "priority must be non-negative")
            except (TypeError, ValueError): return err("VALIDATION_ERROR", "priority must be an integer")
        try:
            if "min_amount" in conditions and Decimal(str(conditions["min_amount"])) < 0: raise ValueError()
            if "max_amount" in conditions and Decimal(str(conditions["max_amount"])) < 0: raise ValueError()
        except Exception: return err("VALIDATION_ERROR", "Approval amounts must be non-negative numbers")
        for key in ("name", "priority", "conditions", "steps", "active"):
            if key in request.data: setattr(rule, key, request.data[key])
        if not rule.name or not isinstance(rule.steps, list) or not rule.steps: return err("VALIDATION_ERROR", "Rule needs a name and at least one step")
        rule.updated_by = request.user
        rule.save()
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="APPROVAL_RULE_UPDATED", object_type="ApprovalRule", object_id=str(rule.id), metadata={"active": rule.active})
        return Response({"id": str(rule.id), "name": rule.name, "priority": rule.priority, "conditions": rule.conditions, "steps": rule.steps, "active": rule.active})

    def delete(self, request, rule_id=None):
        if request.membership.role not in FINANCE: return err("PERMISSION_DENIED", "Finance role required", 403)
        rule = get_object_or_404(ApprovalRule, tenant=request.tenant, id=rule_id)
        rule.active = False
        rule.updated_by = request.user
        rule.save(update_fields=["active", "updated_by", "updated_at"])
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="APPROVAL_RULE_DEACTIVATED", object_type="ApprovalRule", object_id=str(rule.id), metadata={})
        return Response(status=204)


def rule_matches(rule, invoice):
    c = rule.conditions
    amount = invoice.invoice_total
    if "min_amount" in c and amount < Decimal(str(c["min_amount"])): return False
    if "max_amount" in c and amount > Decimal(str(c["max_amount"])): return False
    if c.get("vendor_ids") and str(invoice.vendor_id) not in [str(x) for x in c["vendor_ids"]]: return False
    if c.get("categories") and invoice.category not in c["categories"]: return False
    return True


class ApprovalDelegations(APIView):
    permission_classes = [HasTenantMembership]
    def get(self, request):
        rows = ApprovalDelegation.objects.filter(tenant=request.tenant).order_by("-starts_at")[:200]
        return Response([{"id": str(x.id), "delegator_id": str(x.delegator_id), "delegate_id": str(x.delegate_id), "starts_at": x.starts_at, "ends_at": x.ends_at, "active": x.active} for x in rows])
    def post(self, request):
        delegate_id = request.data.get("delegate_id")
        if not Membership.objects.filter(tenant=request.tenant, user_id=delegate_id, is_active=True).exists(): return err("VALIDATION_ERROR", "Delegate must be an active workspace user")
        if str(request.user.id) == str(delegate_id): return err("VALIDATION_ERROR", "You cannot delegate approvals to yourself")
        try: starts, ends = timezone.datetime.fromisoformat(request.data["starts_at"]), timezone.datetime.fromisoformat(request.data["ends_at"])
        except (KeyError, TypeError, ValueError): return err("VALIDATION_ERROR", "Valid starts_at and ends_at timestamps are required")
        starts = timezone.make_aware(starts) if timezone.is_naive(starts) else starts
        ends = timezone.make_aware(ends) if timezone.is_naive(ends) else ends
        if ends <= starts or ends - starts > timedelta(days=90): return err("VALIDATION_ERROR", "Delegation must be positive and no longer than 90 days")
        row = ApprovalDelegation.objects.create(tenant=request.tenant, delegator=request.user, delegate_id=delegate_id, starts_at=starts, ends_at=ends)
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="APPROVAL_DELEGATED", object_type="ApprovalDelegation", object_id=str(row.id), metadata={"delegate_id": str(delegate_id)})
        return Response({"id": str(row.id), "delegate_id": str(row.delegate_id), "starts_at": starts, "ends_at": ends}, status=201)


class ApprovalStepHistory(APIView):
    permission_classes = [HasTenantMembership]
    def get(self, request, invoice_id):
        invoice = get_object_or_404(Invoice, tenant=request.tenant, id=invoice_id)
        rows = invoice.approval_steps.order_by("workflow_version", "sequence")
        decisions = invoice.approvals.select_related("approver").order_by("decided_at")
        return Response({"steps": [{"id": str(x.id), "workflow_version": x.workflow_version, "sequence": x.sequence, "approver_role": x.approver_role,
            "approver_id": str(x.approver_id) if x.approver_id else None, "delegated_from_id": str(x.delegated_from_id) if x.delegated_from_id else None,
            "status": x.status, "comments": x.comments, "evaluation": x.evaluation, "requested_at": x.requested_at, "decided_at": x.decided_at} for x in rows],
            "decisions": [{"id": str(x.id), "method": x.method, "approver": x.approver.email if x.approver else "Automatic rule", "decision": x.decision, "comments": x.comments, "rule_evaluation": x.rule_evaluation, "decided_at": x.decided_at} for x in decisions]})


class PendingApprovalQueue(APIView):
    permission_classes = [HasTenantMembership]
    def get(self, request):
        from django.db.models import Q
        now = timezone.now()
        role = request.membership.role
        steps = ApprovalStep.objects.filter(tenant=request.tenant, status=ApprovalStep.Status.PENDING).select_related("invoice", "approver")
        eligible = []
        for step in steps.order_by("-workflow_version", "sequence"):
            earlier = ApprovalStep.objects.filter(tenant=request.tenant, invoice=step.invoice, workflow_version=step.workflow_version, status=ApprovalStep.Status.PENDING, sequence__lt=step.sequence).exists()
            if earlier: continue
            is_assigned = step.approver_id == request.user.id or bool(step.approver_role and step.approver_role == role)
            if step.approver_id and ApprovalDelegation.objects.filter(tenant=request.tenant, delegator_id=step.approver_id, delegate=request.user, active=True, starts_at__lte=now, ends_at__gt=now).exists(): is_assigned = True
            if is_assigned and step.invoice.uploaded_by_id != request.user.id: eligible.append(step.invoice)
        step_invoice_ids = set(ApprovalStep.objects.filter(tenant=request.tenant, status=ApprovalStep.Status.PENDING).values_list("invoice_id", flat=True))
        legacy = Invoice.objects.filter(tenant=request.tenant, status=Invoice.Status.APPROVAL_PENDING).exclude(id__in=step_invoice_ids).exclude(uploaded_by=request.user) if role in {"OWNER", "FINANCE", "APPROVER"} else Invoice.objects.none()
        records = list({x.id: x for x in [*eligible, *legacy]}.values())
        from .serializers import InvoiceSerializer
        return Response(InvoiceSerializer(records, many=True, context={"request": request}).data)


class AutoApprovalRules(APIView):
    permission_classes = [HasTenantMembership]
    def get(self, request):
        return Response([{"id": str(x.id), "name": x.name, "enabled": x.enabled, "amount_limit": x.amount_limit, "allowed_vendor_ids": x.allowed_vendor_ids, "conditions": x.conditions} for x in AutoApprovalRule.objects.filter(tenant=request.tenant)])
    def post(self, request):
        if request.membership.role != "OWNER": return err("PERMISSION_DENIED", "Only workspace owner can configure auto-approval", 403)
        name = str(request.data.get("name", "")).strip()
        try: amount = Decimal(str(request.data.get("amount_limit", 0)))
        except Exception: return err("VALIDATION_ERROR", "amount_limit must be a positive number")
        vendor_ids = request.data.get("allowed_vendor_ids", [])
        if not name or amount <= 0 or not isinstance(vendor_ids, list) or not vendor_ids: return err("VALIDATION_ERROR", "Rule must name allowed vendors and a positive amount limit")
        for vendor_id in vendor_ids:
            from vendors.models import Vendor
            if not Vendor.objects.filter(tenant=request.tenant, id=vendor_id).exists(): return err("VALIDATION_ERROR", "All allowed vendors must belong to this workspace")
        row = AutoApprovalRule.objects.create(tenant=request.tenant, name=name, amount_limit=amount, allowed_vendor_ids=[str(x) for x in vendor_ids],
            conditions=request.data.get("conditions", {}), enabled=bool(request.data.get("enabled", False)), created_by=request.user)
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="AUTO_APPROVAL_RULE_CREATED", object_type="AutoApprovalRule", object_id=str(row.id), metadata={"enabled": row.enabled})
        return Response({"id": str(row.id), "name": row.name, "enabled": row.enabled, "amount_limit": row.amount_limit, "allowed_vendor_ids": row.allowed_vendor_ids}, status=201)

    def patch(self, request, rule_id=None):
        if request.membership.role != "OWNER": return err("PERMISSION_DENIED", "Only workspace owner can configure auto-approval", 403)
        row = get_object_or_404(AutoApprovalRule, tenant=request.tenant, id=rule_id)
        proposed_vendors = request.data.get("allowed_vendor_ids", row.allowed_vendor_ids)
        try: proposed_limit = Decimal(str(request.data.get("amount_limit", row.amount_limit)))
        except Exception: return err("VALIDATION_ERROR", "amount_limit must be positive")
        if proposed_limit <= 0 or not isinstance(proposed_vendors, list) or not proposed_vendors: return err("VALIDATION_ERROR", "Auto-approval requires an amount cap and explicit vendors")
        from vendors.models import Vendor
        if any(not Vendor.objects.filter(tenant=request.tenant, id=vendor_id).exists() for vendor_id in proposed_vendors): return err("VALIDATION_ERROR", "Allowed vendors must belong to this workspace")
        if "enabled" in request.data and request.data["enabled"] is True and (not row.allowed_vendor_ids or row.amount_limit <= 0): return err("VALIDATION_ERROR", "Auto-approval requires explicit vendors and a positive amount cap")
        for key in ("name", "enabled", "amount_limit", "allowed_vendor_ids", "conditions"):
            if key in request.data: setattr(row, key, request.data[key])
        row.save()
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="AUTO_APPROVAL_RULE_UPDATED", object_type="AutoApprovalRule", object_id=str(row.id), metadata={"enabled": row.enabled})
        return Response({"id": str(row.id), "name": row.name, "enabled": row.enabled, "amount_limit": row.amount_limit, "allowed_vendor_ids": row.allowed_vendor_ids})


class ExceptionSLASettings(APIView):
    permission_classes = [HasTenantMembership]
    def get(self, request):
        rows = ExceptionSLA.objects.filter(tenant=request.tenant).order_by("exception_code")
        return Response([{"id": str(x.id), "exception_code": x.exception_code, "due_after_hours": x.due_after_hours, "priority": x.priority, "escalation_roles": x.escalation_roles, "active": x.active} for x in rows])
    def post(self, request):
        if request.membership.role not in FINANCE: return err("PERMISSION_DENIED", "Finance role required", 403)
        code = str(request.data.get("exception_code", "")).strip().upper()
        try: hours = int(request.data.get("due_after_hours", 48))
        except (TypeError, ValueError): return err("VALIDATION_ERROR", "due_after_hours must be an integer")
        priority = request.data.get("priority", "MEDIUM")
        roles = request.data.get("escalation_roles", ["OWNER", "FINANCE"])
        from exceptions_app.models import InvoiceException as IE
        allowed_priorities = {x[0] for x in IE._meta.get_field("priority").choices}
        if not code or hours < 1 or hours > 8760 or priority not in allowed_priorities or not isinstance(roles, list) or not roles or any(r not in Membership.Role.values for r in roles): return err("VALIDATION_ERROR", "Invalid SLA configuration")
        row, _ = ExceptionSLA.objects.update_or_create(tenant=request.tenant, exception_code=code, defaults={"due_after_hours": hours, "priority": priority, "escalation_roles": roles, "active": True})
        InvoiceException.objects.filter(tenant=request.tenant, code=code, status__in=["OPEN", "ASSIGNED"]).update(sla_due_at=timezone.now()+timedelta(hours=hours), priority=priority)
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="EXCEPTION_SLA_SAVED", object_type="ExceptionSLA", object_id=str(row.id), metadata={"code": code, "hours": hours})
        return Response({"id": str(row.id), "exception_code": row.exception_code, "due_after_hours": row.due_after_hours, "priority": row.priority, "escalation_roles": row.escalation_roles, "active": row.active}, status=201)


class GRNServiceAcceptance(APIView):
    permission_classes = [HasTenantMembership]
    def patch(self, request, grn_id):
        if request.membership.role not in {"OWNER", "FINANCE", "PURCHASE", "STORE"}: return err("PERMISSION_DENIED", "Purchase or store role required", 403)
        grn = get_object_or_404(GRN, tenant=request.tenant, id=grn_id)
        accepted = request.data.get("service_accepted")
        reference = str(request.data.get("service_acceptance_reference", "")).strip()
        if not isinstance(accepted, bool): return err("VALIDATION_ERROR", "service_accepted must be boolean")
        if accepted and not reference: return err("VALIDATION_ERROR", "Acceptance reference is required when marking services accepted")
        grn.service_accepted = accepted; grn.service_acceptance_reference = reference if accepted else ""
        grn.save(update_fields=["service_accepted", "service_acceptance_reference"])
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="GRN_SERVICE_ACCEPTANCE_UPDATED", object_type="GRN", object_id=str(grn.id), metadata={"accepted": accepted, "reference": grn.service_acceptance_reference})
        return Response({"id": str(grn.id), "service_accepted": grn.service_accepted, "service_acceptance_reference": grn.service_acceptance_reference})


class OverdueExceptions(APIView):
    permission_classes = [HasTenantMembership]
    def get(self, request):
        rows = InvoiceException.objects.filter(tenant=request.tenant, status__in=["OPEN", "ASSIGNED"], sla_due_at__lt=timezone.now()).select_related("invoice", "assigned_to").order_by("sla_due_at")[:500]
        return Response([{"id": str(x.id), "invoice_id": str(x.invoice_id), "invoice_number": x.invoice.invoice_number, "code": x.code, "priority": x.priority, "sla_due_at": x.sla_due_at, "escalation_level": x.escalation_level, "assigned_to_id": str(x.assigned_to_id) if x.assigned_to_id else None} for x in rows])
    def post(self, request):
        if request.membership.role not in FINANCE: return err("PERMISSION_DENIED", "Finance role required", 403)
        now = timezone.now(); count = 0
        rows = InvoiceException.objects.filter(tenant=request.tenant, status__in=["OPEN", "ASSIGNED"], sla_due_at__lt=now).select_related("assigned_to")
        for exc in rows:
            level = exc.escalation_level + 1
            sla = ExceptionSLA.objects.filter(tenant=request.tenant, exception_code=exc.code, active=True).first()
            roles = sla.escalation_roles if sla else ["OWNER", "FINANCE"]
            member = Membership.objects.filter(tenant=request.tenant, is_active=True, role__in=roles).exclude(user=exc.assigned_to).select_related("user").order_by("user_id").first()
            try:
                event, created = ExceptionEscalation.objects.get_or_create(tenant=request.tenant, exception=exc, level=level,
                    defaults={"escalated_to": member.user if member else None, "reason": "SLA deadline exceeded"})
            except Exception:
                continue
            if not created: continue
            exc.escalation_level = level
            exc.priority = "CRITICAL" if level >= 3 else "HIGH"
            exc.save(update_fields=["escalation_level", "priority"])
            if member: notify(request.tenant, member.user, "Exception escalated", f"{exc.code} is overdue for invoice {exc.invoice_id}.", "/exceptions")
            AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="EXCEPTION_ESCALATED", object_type="Exception", object_id=str(exc.id), metadata={"level": level, "escalated_to": str(member.user_id) if member else None})
            count += 1
        return Response({"escalated": count})


class FollowUps(APIView):
    permission_classes = [HasTenantMembership]
    def get(self, request, invoice_id=None):
        if invoice_id is None:
            rows = VendorFollowUpDraft.objects.filter(tenant=request.tenant).select_related("invoice").order_by("-created_at")[:200]
            return Response([{"id": str(x.id), "invoice_id": str(x.invoice_id), "invoice_number": x.invoice.invoice_number, "recipient": x.recipient, "subject": x.subject, "body": x.body, "status": x.status, "created_at": x.created_at, "sent_at": x.sent_at} for x in rows])
        invoice = get_object_or_404(Invoice, tenant=request.tenant, id=invoice_id)
        return Response([{"id": str(x.id), "recipient": x.recipient, "subject": x.subject, "body": x.body, "status": x.status, "created_at": x.created_at, "sent_at": x.sent_at} for x in invoice.followups.order_by("-created_at")])
    def post(self, request, invoice_id=None):
        if request.membership.role not in FINANCE: return err("PERMISSION_DENIED", "Finance role required", 403)
        if invoice_id is None: invoice_id = request.data.get("invoice_id")
        if not invoice_id: return err("VALIDATION_ERROR", "invoice_id is required")
        invoice = get_object_or_404(Invoice.objects.select_related("vendor"), tenant=request.tenant, id=invoice_id)
        recipient = str(request.data.get("recipient") or getattr(invoice.vendor, "contact_email", "")).strip()
        subject = str(request.data.get("subject") or f"Invoice query: {invoice.invoice_number}").strip()
        body = str(request.data.get("body") or f"Hello {invoice.vendor.name if invoice.vendor else invoice.supplier_name},\n\nWe are reviewing invoice {invoice.invoice_number}. Please help us clarify the outstanding query.\n\nRegards,\n{request.tenant.name}")
        row = VendorFollowUpDraft.objects.create(tenant=request.tenant, invoice=invoice, recipient=recipient, subject=subject, body=body, created_by=request.user)
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="VENDOR_FOLLOWUP_DRAFTED", object_type="VendorFollowUpDraft", object_id=str(row.id), metadata={"invoice_id": str(invoice.id)})
        return Response({"id": str(row.id), "recipient": row.recipient, "subject": row.subject, "body": row.body, "status": row.status}, status=201)


class FollowUpDetail(APIView):
    permission_classes = [HasTenantMembership]
    def patch(self, request, followup_id):
        if request.membership.role not in FINANCE: return err("PERMISSION_DENIED", "Finance role required", 403)
        row = get_object_or_404(VendorFollowUpDraft, tenant=request.tenant, id=followup_id)
        if row.status in ("SENT", "CANCELLED"): return err("STATE_CONFLICT", "This follow-up is already closed", 409)
        for key in ("recipient", "subject", "body"):
            if key in request.data: setattr(row, key, request.data[key])
        row.save()
        if request.data.get("send") is True:
            if not row.recipient: return err("VALIDATION_ERROR", "Set a recipient before sending")
            try: sent = send_mail(row.subject, row.body, settings.DEFAULT_FROM_EMAIL, [row.recipient], fail_silently=False)
            except Exception: return err("SERVICE_UNAVAILABLE", "Email delivery failed; the draft remains available to retry", 503)
            if not sent: return err("SERVICE_UNAVAILABLE", "Email backend did not accept the message", 503)
            row.status = "SENT"; row.sent_by = request.user; row.sent_at = timezone.now(); row.save(update_fields=["status", "sent_by", "sent_at"])
            AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="VENDOR_FOLLOWUP_SENT", object_type="VendorFollowUpDraft", object_id=str(row.id), metadata={"recipient": row.recipient})
        else:
            AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="VENDOR_FOLLOWUP_EDITED", object_type="VendorFollowUpDraft", object_id=str(row.id), metadata={})
        return Response({"id": str(row.id), "recipient": row.recipient, "subject": row.subject, "body": row.body, "status": row.status, "sent_at": row.sent_at})


class CustomFields(APIView):
    permission_classes = [HasTenantMembership]
    def get(self, request):
        return Response([{"id": str(x.id), "name": x.name, "key": x.key, "field_type": x.field_type, "required": x.required, "options": x.options, "active": x.active} for x in CustomFieldDefinition.objects.filter(tenant=request.tenant).order_by("name")])
    def post(self, request):
        if request.membership.role not in FINANCE: return err("PERMISSION_DENIED", "Finance role required", 403)
        name = str(request.data.get("name", "")).strip(); key = slugify(request.data.get("key") or name).replace("-", "_")
        field_type = request.data.get("field_type", "TEXT"); options = request.data.get("options", [])
        if not name or not key or field_type not in CustomFieldDefinition.Type.values: return err("VALIDATION_ERROR", "name, key and supported field_type are required")
        if field_type == "CHOICE" and (not isinstance(options, list) or not options): return err("VALIDATION_ERROR", "Choice fields require options")
        required = request.data.get("required", False)
        if not isinstance(required, bool): return err("VALIDATION_ERROR", "required must be boolean")
        row = CustomFieldDefinition.objects.create(tenant=request.tenant, name=name, key=key, field_type=field_type, required=required, options=options)
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="CUSTOM_FIELD_CREATED", object_type="CustomFieldDefinition", object_id=str(row.id), metadata={"key": key, "type": field_type})
        return Response({"id": str(row.id), "name": row.name, "key": row.key, "field_type": row.field_type, "required": row.required, "options": row.options}, status=201)


class InvoiceCustomValues(APIView):
    permission_classes = [HasTenantMembership]
    def get(self, request, invoice_id):
        invoice = get_object_or_404(Invoice, tenant=request.tenant, id=invoice_id)
        return Response({x.definition.key: {"value": x.value, "type": x.definition.field_type} for x in invoice.custom_field_values.select_related("definition")})
    def patch(self, request, invoice_id):
        if request.membership.role not in FINANCE: return err("PERMISSION_DENIED", "Finance role required", 403)
        invoice = get_object_or_404(Invoice, tenant=request.tenant, id=invoice_id)
        if not isinstance(request.data, dict): return err("VALIDATION_ERROR", "Custom field values must be an object")
        definitions = {x.key: x for x in CustomFieldDefinition.objects.filter(tenant=request.tenant, active=True)}
        if set(request.data) - definitions.keys(): return err("VALIDATION_ERROR", "One or more custom field keys are unknown")
        for key, value in request.data.items():
            d = definitions[key]
            valid = (d.field_type == "TEXT" and isinstance(value, str)) or (d.field_type == "NUMBER" and isinstance(value, (int, float)) and not isinstance(value, bool)) or (d.field_type == "BOOLEAN" and isinstance(value, bool)) or (d.field_type == "DATE" and (value is None or (isinstance(value, str) and _valid_iso_date(value)))) or (d.field_type == "CHOICE" and value in d.options)
            if value is None and not d.required: valid = True
            if not valid: return err("VALIDATION_ERROR", f"Value for {key} does not match {d.field_type}")
            InvoiceCustomFieldValue.objects.update_or_create(tenant=request.tenant, invoice=invoice, definition=d, defaults={"value": value})
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="INVOICE_CUSTOM_FIELDS_UPDATED", object_type="Invoice", object_id=str(invoice.id), metadata={"keys": sorted(request.data)})
        return self.get(request, invoice_id)


def _valid_iso_date(value):
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


class Notifications(APIView):
    permission_classes = [HasTenantMembership]
    def get(self, request):
        rows = Notification.objects.filter(tenant=request.tenant, recipient=request.user).order_by("-created_at")[:200]
        return Response([{"id": str(x.id), "status": x.status, "payload": x.payload, "created_at": x.created_at, "read_at": x.read_at} for x in rows])
    def patch(self, request, notification_id=None):
        if notification_id is None: return err("METHOD_NOT_ALLOWED", "Use a notification read endpoint", 405)
        row = get_object_or_404(Notification, tenant=request.tenant, recipient=request.user, id=notification_id)
        row.read_at = timezone.now(); row.status = "READ"; row.save(update_fields=["read_at", "status"])
        return Response({"id": str(row.id), "status": row.status, "read_at": row.read_at})


class NotificationPreferences(APIView):
    permission_classes = [HasTenantMembership]
    allowed = {"approvals", "exceptions", "payments", "email", "fleet", "daily_digest"}
    def get(self, request):
        obj, _ = NotificationPreference.objects.get_or_create(tenant=request.tenant, user=request.user)
        return Response({key: obj.preferences.get(key, True) for key in sorted(self.allowed)})
    def patch(self, request):
        if not request.data or set(request.data) - self.allowed or any(not isinstance(v, bool) for v in request.data.values()): return err("VALIDATION_ERROR", "Set boolean values for supported notification preferences")
        obj, _ = NotificationPreference.objects.get_or_create(tenant=request.tenant, user=request.user)
        obj.preferences.update(request.data); obj.save(update_fields=["preferences", "updated_at"])
        return self.get(request)


class Reports(APIView):
    permission_classes = [HasTenantMembership]
    def get(self, request, report_name):
        invoices = Invoice.objects.filter(tenant=request.tenant)
        for key, lookup in (("from", "created_at__date__gte"), ("to", "created_at__date__lte")):
            value = request.query_params.get(key)
            if value:
                try: date.fromisoformat(value)
                except ValueError: return err("VALIDATION_ERROR", f"{key} must be an ISO date")
                invoices = invoices.filter(**{lookup: value})
        today = timezone.localdate()
        if report_name == "invoice-aging":
            buckets = {"current": {"count": 0, "amount": Decimal("0")}, "1_30_days": {"count": 0, "amount": Decimal("0")}, "31_60_days": {"count": 0, "amount": Decimal("0")}, "61_90_days": {"count": 0, "amount": Decimal("0")}, "over_90_days": {"count": 0, "amount": Decimal("0")}}
            for invoice in with_invoice_balances(invoices.exclude(payment_status="CANCELLED")).filter(outstanding_balance__gt=0).select_related("vendor"):
                days = (today - invoice.due_date).days if invoice.due_date else 0
                key = "current" if days <= 0 else "1_30_days" if days <= 30 else "31_60_days" if days <= 60 else "61_90_days" if days <= 90 else "over_90_days"
                due = invoice.outstanding_balance
                buckets[key]["count"] += 1; buckets[key]["amount"] += max(due, Decimal("0"))
            return self._response(request, buckets)
        if report_name == "vendor-outstanding":
            totals = {}
            for invoice in with_invoice_balances(invoices.exclude(payment_status="CANCELLED")).filter(outstanding_balance__gt=0).select_related("vendor"):
                due = invoice.outstanding_balance
                key = invoice.vendor.name if invoice.vendor else "Unassigned vendor"
                item = totals.setdefault(key, {"vendor": key, "invoice_count": 0, "outstanding": Decimal("0")})
                item["invoice_count"] += 1; item["outstanding"] += max(due, Decimal("0"))
            return self._response(request, sorted(totals.values(), key=lambda x: x["vendor"]))
        if report_name == "exception-summary":
            return self._response(request, list(InvoiceException.objects.filter(tenant=request.tenant).values("code", "priority", "status").annotate(count=Count("id")).order_by("code")))
        if report_name == "payment-forecast":
            totals = {}
            for invoice in with_invoice_balances(invoices.exclude(payment_status="CANCELLED").filter(due_date__isnull=False)).filter(outstanding_balance__gt=0):
                due = invoice.outstanding_balance
                key = str(invoice.due_date); item = totals.setdefault(key, {"due_date": key, "invoice_count": 0, "amount": Decimal("0")}); item["invoice_count"] += 1; item["amount"] += max(due, Decimal("0"))
            return self._response(request, sorted(totals.values(), key=lambda x: x["due_date"]))
        if report_name == "month-end-readiness":
            open_exceptions = InvoiceException.objects.filter(tenant=request.tenant, status__in=["OPEN", "ASSIGNED"], blocking=True).count()
            pending_dupes = DuplicateCheck.objects.filter(tenant=request.tenant, decision="PENDING").count()
            pending_notes = CreditDebitNote.objects.filter(tenant=request.tenant, status="PENDING").count()
            approvals = invoices.filter(status="APPROVAL_PENDING").count()
            result = {"unresolved_blocking_exceptions": open_exceptions, "pending_duplicate_reviews": pending_dupes,
                "pending_financial_notes": pending_notes, "invoices_awaiting_approval": approvals,
                "payment_ready": invoices.filter(status="PAYMENT_READY").count(), "ready": not any([open_exceptions, pending_dupes, pending_notes, approvals])}
            return self._response(request, result)
        return err("NOT_FOUND", "Unknown report", 404)

    def _response(self, request, data):
        if request.query_params.get("export") != "csv": return Response(data)
        rows = data if isinstance(data, list) else [data] if isinstance(data, dict) else []
        output = io.StringIO(); keys = sorted({key for row in rows for key in row})
        writer = csv.DictWriter(output, fieldnames=keys or ["value"]); writer.writeheader()
        for row in rows: writer.writerow({key: row.get(key, "") for key in keys})
        response = HttpResponse(output.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="kriyopay-{request.resolver_match.kwargs.get("report_name", "report")}.csv"'
        return response


class BulkJobs(APIView):
    permission_classes = [HasTenantMembership]
    allowed_operations = {"ASSIGN_EXCEPTIONS", "RESOLVE_EXCEPTIONS"}
    def get(self, request, job_id=None):
        qs = BulkJob.objects.filter(tenant=request.tenant)
        if job_id:
            row = get_object_or_404(qs, id=job_id)
            return Response({"id": str(row.id), "operation": row.operation, "status": row.status, "preview": row.preview, "result": row.result, "expires_at": row.expires_at})
        return Response([{"id": str(x.id), "operation": x.operation, "status": x.status, "created_at": x.created_at, "preview": x.preview, "result": x.result} for x in qs.order_by("-created_at")[:100]])
    def post(self, request, job_id=None):
        if request.membership.role not in FINANCE and request.membership.role not in {"PURCHASE", "STORE"}: return err("PERMISSION_DENIED", "Operational role required", 403)
        if job_id:
            with transaction.atomic():
                job = get_object_or_404(BulkJob.objects.select_for_update(), tenant=request.tenant, id=job_id)
                if job.status != BulkJob.Status.PREVIEW: return err("STATE_CONFLICT", "Bulk preview is no longer commit-ready", 409)
                if job.expires_at <= timezone.now() or not secrets.compare_digest(str(request.data.get("preview_token", "")), job.preview_token): return err("STATE_CONFLICT", "Preview expired or token mismatched; create a fresh preview", 409)
                ids = job.target_ids
                rows = list(InvoiceException.objects.filter(tenant=request.tenant, id__in=ids, status__in=["OPEN", "ASSIGNED"]))
                if len(rows) != len(ids): return err("STATE_CONFLICT", "Queue changed since preview; refresh and preview again", 409)
                member = None
                if job.operation == "ASSIGN_EXCEPTIONS":
                    member = Membership.objects.filter(tenant=request.tenant, user_id=job.preview["assigned_to_id"], is_active=True).first()
                    if not member: return err("VALIDATION_ERROR", "Assignee is no longer an active workspace member")
                result = []
                for exc in rows:
                    if job.operation == "ASSIGN_EXCEPTIONS":
                        exc.assigned_to = member.user; exc.status = "ASSIGNED"; exc.save(update_fields=["assigned_to", "status"])
                    else:
                        exc.status = "RESOLVED"; exc.resolution_note = job.preview["resolution_note"]; exc.resolved_at = timezone.now(); exc.save(update_fields=["status", "resolution_note", "resolved_at"])
                    AuditLog.objects.create(tenant=request.tenant, actor=request.user, action=f"BULK_{job.operation}", object_type="Exception", object_id=str(exc.id), metadata={"bulk_job_id": str(job.id)})
                    result.append(str(exc.id))
                if job.operation == "RESOLVE_EXCEPTIONS":
                    for invoice in {x.invoice for x in rows}:
                        if invoice.status == Invoice.Status.EXCEPTION and not invoice.exceptions.filter(blocking=True).exclude(status__in=["RESOLVED", "OVERRIDDEN"]).exists():
                            invoice.status = Invoice.Status.MATCHED; invoice.save(update_fields=["status", "updated_at"])
                job.status = BulkJob.Status.COMPLETED; job.committed_at = timezone.now(); job.result = {"completed_ids": result}; job.save(update_fields=["status", "committed_at", "result"])
                return Response({"id": str(job.id), "status": job.status, "result": job.result})
        operation = request.data.get("operation"); ids = request.data.get("ids")
        if operation not in self.allowed_operations or not isinstance(ids, list) or not ids: return err("VALIDATION_ERROR", "Supported operation and non-empty ids are required")
        rows = list(InvoiceException.objects.filter(tenant=request.tenant, id__in=ids, status__in=["OPEN", "ASSIGNED"]))
        if len(rows) != len(set(str(x) for x in ids)): return err("NOT_FOUND", "One or more exceptions are unavailable in this workspace", 404)
        preview = {"count": len(rows), "exception_ids": [str(x.id) for x in rows]}
        if operation == "ASSIGN_EXCEPTIONS":
            user_id = request.data.get("assigned_to_id")
            if not Membership.objects.filter(tenant=request.tenant, user_id=user_id, is_active=True).exists(): return err("VALIDATION_ERROR", "Assignee must be an active workspace member")
            preview["assigned_to_id"] = str(user_id)
        if operation == "RESOLVE_EXCEPTIONS":
            note = str(request.data.get("resolution_note", "")).strip()
            if not note: return err("VALIDATION_ERROR", "A resolution_note is required for bulk resolution")
            preview["resolution_note"] = note[:2000]
        token = secrets.token_urlsafe(32)
        job = BulkJob.objects.create(tenant=request.tenant, created_by=request.user, operation=operation, target_ids=[str(x.id) for x in rows], preview=preview, preview_token=token, expires_at=timezone.now()+timedelta(minutes=15))
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="BULK_OPERATION_PREVIEWED", object_type="BulkJob", object_id=str(job.id), metadata={"operation": operation, "count": len(rows)})
        return Response({"id": str(job.id), "status": job.status, "preview_token": token, "preview": preview, "expires_at": job.expires_at}, status=201)
