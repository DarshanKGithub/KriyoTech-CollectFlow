from decimal import Decimal

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import HasTenantMembership
from audit.models import AuditLog
from invoices.models import Invoice
from payments.models import PayoutInstruction
from payments.services import allocated_total, invoice_net_payable, money
from vendors.models import Vendor


FINANCE = {"OWNER", "FINANCE"}
REVIEWERS = FINANCE | {"APPROVER"}
READERS = REVIEWERS | {"AUDITOR"}


def payout_payload(row):
    return {
        "id": str(row.id), "invoice_id": str(row.invoice_id),
        "invoice_number": row.invoice.invoice_number,
        "vendor_id": str(row.vendor_id), "vendor_name": row.vendor.name,
        "amount": format(row.amount, ".2f"), "currency": row.currency,
        "status": row.status, "requested_by": row.requested_by.get_full_name() or row.requested_by.email if row.requested_by else "Former user",
        "requested_by_id": str(row.requested_by_id) if row.requested_by_id else None,
        "reviewed_by": row.reviewed_by.get_full_name() or row.reviewed_by.email if row.reviewed_by else "",
        "review_note": row.review_note, "created_at": row.created_at.isoformat(),
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        "execution": "Not sent to a bank or payment provider",
    }


class PayoutInstructionCollection(APIView):
    """Create/list reviewed payout instructions. No endpoint here moves money."""
    permission_classes = [HasTenantMembership]

    def get(self, request):
        if request.membership.role not in READERS:
            return Response({"error": "Finance or auditor role required."}, status=403)
        rows = PayoutInstruction.objects.filter(tenant=request.tenant).select_related(
            "invoice", "vendor", "requested_by", "reviewed_by"
        ).order_by("-created_at")[:200]
        return Response({"results": [payout_payload(row) for row in rows], "count": len(rows), "provider_connected": False})

    @transaction.atomic
    def post(self, request):
        if request.membership.role not in FINANCE:
            return Response({"error": "Owner or finance role required to request a payout."}, status=403)
        if set(request.data) != {"invoice_id", "amount", "idempotency_key"}:
            raise ValidationError("Provide only invoice_id, amount and idempotency_key.")
        try:
            key = request.data["idempotency_key"]
            from uuid import UUID
            key = UUID(str(key))
        except (ValueError, TypeError, AttributeError):
            raise ValidationError({"idempotency_key": "Provide a valid UUID request key."}) from None
        try:
            invoice_id = UUID(str(request.data["invoice_id"]))
        except (ValueError, TypeError, AttributeError, KeyError):
            raise ValidationError({"invoice_id": "Choose a valid workspace invoice."}) from None
        amount = money(request.data.get("amount"))
        existing = PayoutInstruction.objects.filter(tenant=request.tenant, idempotency_key=key).select_related("invoice", "vendor", "requested_by", "reviewed_by").first()
        if existing:
            if existing.invoice_id != invoice_id or existing.amount != amount:
                return Response({"error": "This request key was already used for a different payout."}, status=409)
            return Response(payout_payload(existing), status=200)

        invoice = get_object_or_404(Invoice.objects.select_for_update(of=("self",)), id=invoice_id, tenant=request.tenant)
        vendor = Vendor.objects.filter(id=invoice.vendor_id, tenant=request.tenant, approved=True).first()
        if not vendor:
            raise ValidationError({"invoice_id": "The invoice must have an approved workspace supplier."})
        if invoice.status not in {Invoice.Status.PAYMENT_READY, Invoice.Status.EXPORTED} or invoice.payment_status == "CANCELLED":
            return Response({"error": "Only approved, payment-ready invoices can have a payout instruction."}, status=409)
        if invoice.exceptions.filter(blocking=True).exclude(status__in=["RESOLVED", "OVERRIDDEN"]).exists():
            return Response({"error": "Resolve blocking invoice exceptions before requesting a payout."}, status=409)
        if PayoutInstruction.objects.filter(tenant=request.tenant, invoice=invoice, status__in=[PayoutInstruction.Status.AWAITING_APPROVAL, PayoutInstruction.Status.APPROVED]).exists():
            return Response({"error": "This invoice already has an active payout instruction."}, status=409)
        outstanding = invoice_net_payable(invoice) - allocated_total(invoice)
        if amount > outstanding:
            raise ValidationError({"amount": f"Amount cannot exceed the current outstanding balance ({outstanding:.2f} INR)."})
        try:
            with transaction.atomic():
                row = PayoutInstruction.objects.create(tenant=request.tenant, invoice=invoice, vendor=vendor,
                    amount=amount, currency="INR", idempotency_key=key, requested_by=request.user)
                AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="PAYOUT_INSTRUCTION_REQUESTED",
                    object_type="PayoutInstruction", object_id=str(row.id), metadata={"invoice_id": str(invoice.id), "amount": str(amount), "currency": row.currency})
        except IntegrityError:
            row = PayoutInstruction.objects.select_related("invoice", "vendor", "requested_by", "reviewed_by").get(tenant=request.tenant, idempotency_key=key)
            if row.invoice_id != invoice.id or row.amount != amount:
                return Response({"error": "This request key was already used for a different payout."}, status=409)
            return Response(payout_payload(row), status=200)
        return Response(payout_payload(row), status=201)


class PayoutInstructionDecision(APIView):
    permission_classes = [HasTenantMembership]

    @transaction.atomic
    def post(self, request, instruction_id):
        if request.membership.role not in REVIEWERS:
            return Response({"error": "An owner, finance user or approver must review the payout."}, status=403)
        if set(request.data) != {"decision", "note"}:
            raise ValidationError("Provide decision and note.")
        decision = request.data.get("decision")
        note = str(request.data.get("note", "")).strip()
        if decision not in {"APPROVE", "REJECT"}:
            raise ValidationError({"decision": "Choose APPROVE or REJECT."})
        if decision == "REJECT" and len(note) < 8:
            raise ValidationError({"note": "Give a rejection reason of at least 8 characters."})
        row = get_object_or_404(PayoutInstruction.objects.select_for_update(), id=instruction_id, tenant=request.tenant)
        if row.status != PayoutInstruction.Status.AWAITING_APPROVAL:
            return Response({"error": "Only an instruction awaiting approval can be reviewed."}, status=409)
        if row.requested_by_id == request.user.id:
            return Response({"error": "The requester cannot approve or reject their own payout instruction."}, status=403)
        row.reviewed_by = request.user
        row.reviewed_at = timezone.now()
        row.review_note = note[:1000]
        audit_action = "PAYOUT_INSTRUCTION_APPROVED" if decision == "APPROVE" else "PAYOUT_INSTRUCTION_REJECTED"
        if decision == "APPROVE":
            invoice = Invoice.objects.select_for_update(of=("self",)).filter(id=row.invoice_id, tenant=request.tenant).first()
            outstanding = invoice_net_payable(invoice) - allocated_total(invoice) if invoice else Decimal("0")
            valid_state = invoice and invoice.status in {Invoice.Status.PAYMENT_READY, Invoice.Status.EXPORTED} and invoice.payment_status != "CANCELLED"
            if not valid_state or row.amount > outstanding or invoice.exceptions.filter(blocking=True).exclude(status__in=["RESOLVED", "OVERRIDDEN"]).exists():
                row.status = PayoutInstruction.Status.STALE
                audit_action = "PAYOUT_INSTRUCTION_STALE"
                row.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note", "updated_at"])
                AuditLog.objects.create(tenant=request.tenant, actor=request.user, action=audit_action, object_type="PayoutInstruction", object_id=str(row.id), metadata={"reason": "invoice state or outstanding balance changed"})
                row = PayoutInstruction.objects.select_related("invoice", "vendor", "requested_by", "reviewed_by").get(pk=row.pk)
                return Response({**payout_payload(row), "error": "Invoice state or outstanding balance changed; create a new instruction after review."}, status=409)
            row.status = PayoutInstruction.Status.APPROVED
        else:
            row.status = PayoutInstruction.Status.REJECTED
        row.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note", "updated_at"])
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action=audit_action, object_type="PayoutInstruction", object_id=str(row.id), metadata={"note": row.review_note, "amount": str(row.amount), "currency": row.currency})
        row = PayoutInstruction.objects.select_related("invoice", "vendor", "requested_by", "reviewed_by").get(pk=row.pk)
        return Response({**payout_payload(row), "internally_approved": row.status == PayoutInstruction.Status.APPROVED,
                         "provider_message": "Approved internally only. No provider is connected and no transfer was sent."})
