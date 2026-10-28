from decimal import Decimal

from django.db import transaction
from django.db.models import Sum, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import HasTenantMembership
from audit.models import AuditLog
from invoices.models import DuplicateCheck, Invoice
from matching.models import MatchingSetting
from payments.models import CreditDebitNote, Payment, PaymentAllocation
from payments.serializers import CreditDebitNoteSerializer, PaymentSerializer
from payments.services import invoice_net_payable, record_payment, allocated_total
from vendors.models import Vendor, VendorAlias


def finance_role(request):
    return request.membership.role in ("OWNER", "FINANCE")


class DuplicateReview(APIView):
    permission_classes = [HasTenantMembership]

    def get(self, request):
        qs = DuplicateCheck.objects.filter(tenant=request.tenant).select_related("invoice", "candidate_invoice")
        decision = request.query_params.get("decision")
        if decision:
            qs = qs.filter(decision=decision)
        return Response([{"id": str(row.id), "invoice_id": str(row.invoice_id),
            "invoice_number": row.invoice.invoice_number, "candidate_invoice_id": str(row.candidate_invoice_id),
            "candidate_number": row.candidate_invoice.invoice_number, "kind": row.kind,
            "score": row.score, "reasons": row.reasons, "decision": row.decision,
            "decision_note": row.decision_note} for row in qs.order_by("-created_at")[:200]])

    def post(self, request, check_id=None):
        if check_id is None:
            return Response({"error": {"code": "METHOD_NOT_ALLOWED", "message": "Use the decision endpoint for a duplicate review"}}, status=405)
        if not finance_role(request):
            return Response({"error": {"code": "PERMISSION_DENIED", "message": "Finance role required"}}, status=403)
        check = get_object_or_404(DuplicateCheck, id=check_id, tenant=request.tenant)
        decision = request.data.get("decision")
        if decision not in (DuplicateCheck.Decision.CONFIRM_DUPLICATE, DuplicateCheck.Decision.NOT_DUPLICATE):
            return Response({"error": {"code": "VALIDATION_ERROR", "message": "Choose CONFIRM_DUPLICATE or NOT_DUPLICATE"}}, status=400)
        check.decision = decision
        check.decision_note = str(request.data.get("note", ""))[:2000]
        check.decided_by = request.user
        check.decided_at = timezone.now()
        check.save(update_fields=["decision", "decision_note", "decided_by", "decided_at"])
        invoice = check.invoice
        invoice.duplicate_review_complete = not invoice.duplicate_checks.filter(decision=DuplicateCheck.Decision.PENDING).exists()
        if decision == DuplicateCheck.Decision.CONFIRM_DUPLICATE:
            invoice.status = Invoice.Status.EXCEPTION
        invoice.save(update_fields=["duplicate_review_complete", "status", "updated_at"])
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="DUPLICATE_REVIEWED",
            object_type="DuplicateCheck", object_id=str(check.id), metadata={"decision": decision, "note": check.decision_note})
        return Response({"id": str(check.id), "decision": check.decision, "duplicate_review_complete": invoice.duplicate_review_complete})


class MatchingControls(APIView):
    permission_classes = [HasTenantMembership]

    def _payload(self, row):
        return {"rate_tolerance_percent": row.rate_tolerance_percent, "rate_tolerance_amount": row.rate_tolerance_amount,
            "quantity_tolerance_percent": row.quantity_tolerance_percent, "quantity_tolerance_amount": row.quantity_tolerance_amount,
            "tax_tolerance_percent": row.tax_tolerance_percent, "over_receipt_tolerance_percent": row.over_receipt_tolerance_percent, "matching_priority": row.matching_priority,
            "allow_partial_grn": row.allow_partial_grn, "require_service_acceptance": row.require_service_acceptance,
            "version": row.version, "updated_at": row.updated_at}

    def get(self, request):
        row, _ = MatchingSetting.objects.get_or_create(tenant=request.tenant)
        return Response(self._payload(row))

    def patch(self, request):
        if not finance_role(request):
            return Response({"error": {"code": "PERMISSION_DENIED", "message": "Finance role required"}}, status=403)
        fields = {"rate_tolerance_percent", "rate_tolerance_amount", "quantity_tolerance_percent",
            "quantity_tolerance_amount", "tax_tolerance_percent", "over_receipt_tolerance_percent", "matching_priority", "allow_partial_grn", "require_service_acceptance"}
        if not request.data or set(request.data) - fields:
            return Response({"error": {"code": "VALIDATION_ERROR", "message": "Unsupported matching setting"}}, status=400)
        row, _ = MatchingSetting.objects.get_or_create(tenant=request.tenant)
        for key, value in request.data.items():
            if key in fields - {"matching_priority", "allow_partial_grn", "require_service_acceptance"}:
                try:
                    value = Decimal(str(value))
                except Exception:
                    return Response({"error": {"code": "VALIDATION_ERROR", "message": f"{key} must be numeric"}}, status=400)
                if value < 0 or (key.endswith("percent") and value > 100):
                    return Response({"error": {"code": "VALIDATION_ERROR", "message": f"Invalid value for {key}"}}, status=400)
            if key in {"allow_partial_grn", "require_service_acceptance"} and not isinstance(value, bool):
                return Response({"error": {"code": "VALIDATION_ERROR", "message": f"{key} must be boolean"}}, status=400)
            if key == "matching_priority" and (not isinstance(value, list) or any(v not in ("GSTIN", "NAME", "ALIAS", "EMAIL_DOMAIN") for v in value)):
                return Response({"error": {"code": "VALIDATION_ERROR", "message": "matching_priority must be a list of supported signals"}}, status=400)
            setattr(row, key, value)
        row.version += 1
        row.save()
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="MATCHING_SETTINGS_UPDATED", object_type="MatchingSetting", object_id=str(row.id), metadata={"version": row.version, "fields": sorted(request.data)})
        return Response(self._payload(row))


class VendorAliasCollection(APIView):
    permission_classes = [HasTenantMembership]

    def get(self, request):
        qs = VendorAlias.objects.filter(tenant=request.tenant).select_related("vendor").order_by("alias")
        return Response([{"id": str(a.id), "vendor_id": str(a.vendor_id), "vendor_name": a.vendor.name,
            "alias": a.alias, "normalized_alias": a.normalized_alias, "kind": a.kind} for a in qs])

    def post(self, request):
        if not finance_role(request):
            return Response({"error": {"code": "PERMISSION_DENIED", "message": "Finance role required"}}, status=403)
        alias = str(request.data.get("alias", "")).strip()
        kind = request.data.get("kind", "NAME")
        if not alias or kind not in VendorAlias.Kind.values:
            return Response({"error": {"code": "VALIDATION_ERROR", "message": "alias and valid kind are required"}}, status=400)
        vendor = get_object_or_404(Vendor, id=request.data.get("vendor_id"), tenant=request.tenant)
        normalized = alias.casefold().strip().lstrip("@")
        obj, created = VendorAlias.objects.get_or_create(tenant=request.tenant, normalized_alias=normalized, kind=kind,
            defaults={"vendor": vendor, "alias": alias})
        if not created and obj.vendor_id != vendor.id:
            return Response({"error": {"code": "STATE_CONFLICT", "message": "Alias already belongs to another vendor"}}, status=409)
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="VENDOR_ALIAS_CREATED", object_type="VendorAlias", object_id=str(obj.id), metadata={"vendor_id": str(vendor.id), "kind": kind})
        return Response({"id": str(obj.id), "vendor_id": str(vendor.id), "alias": obj.alias, "kind": kind}, status=201 if created else 200)


class PaymentRegister(APIView):
    permission_classes = [HasTenantMembership]

    def get(self, request):
        qs = Payment.objects.filter(tenant=request.tenant).prefetch_related("allocations").order_by("-paid_at", "-created_at")
        if request.query_params.get("paginated") == "1":
            from datetime import date
            from rest_framework.exceptions import ValidationError, PermissionDenied
            from phase3.reconciliation import identifier
            if request.membership.branch_scope_enabled: raise PermissionDenied("Workspace-wide finance access is required for the payment register.")
            qs = qs.filter(cancelled_at__isnull=True).select_related("vendor")
            search = request.query_params.get("search", "").strip()
            if len(search) > 120: raise ValidationError("Search is limited to 120 characters.")
            if search: qs = qs.filter(Q(reference_number__icontains=search)|Q(vendor__name__icontains=search)|Q(remarks__icontains=search))
            dates = {}
            for key in ("from", "to"):
                if request.query_params.get(key):
                    try: dates[key] = date.fromisoformat(request.query_params[key])
                    except (ValueError, TypeError): raise ValidationError("Use ISO dates for payment filters.") from None
            if len(dates) == 2 and dates["from"] > dates["to"]: raise ValidationError("End date must follow start date.")
            if "from" in dates: qs = qs.filter(paid_at__gte=dates["from"])
            if "to" in dates: qs = qs.filter(paid_at__lte=dates["to"])
            if request.query_params.get("account_id"): qs = qs.filter(source_account_id=identifier(request.query_params["account_id"]))
            try: page = int(request.query_params.get("page", 1)); size = int(request.query_params.get("page_size", 25))
            except (ValueError, TypeError): raise ValidationError("Invalid payment page.") from None
            if page < 1 or size not in {5, 10, 25, 50, 100}: raise ValidationError("Use a positive page and a supported page size.")
            sort = request.query_params.get("sort", "-paid_at")
            if sort.lstrip("-") not in {"paid_at", "amount", "reference_number", "mode"}: raise ValidationError("Invalid payment sort column.")
            count = qs.count()
            total = qs.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
            rows = qs.order_by(sort, "id")[(page-1)*size:page*size]
            return Response({"count": count, "results": PaymentSerializer(rows, many=True).data,
                "total_recorded_amount": format(Decimal(total).quantize(Decimal("0.01")), "f"), "ledger_currency": "INR", "page": page, "page_size": size})
        return Response(PaymentSerializer(qs[:200], many=True).data)

    @transaction.atomic
    def post(self, request):
        if not finance_role(request):
            return Response({"error": {"code": "PERMISSION_DENIED", "message": "Finance role required"}}, status=403)
        serializer = PaymentSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        allocations = data.pop("allocations")
        payment, created = record_payment(tenant=request.tenant, actor=request.user, data=data, allocations=allocations)
        return Response(PaymentSerializer(payment).data, status=201 if created else 200)


class CreditDebitNoteCollection(APIView):
    permission_classes = [HasTenantMembership]

    def get(self, request):
        return Response(CreditDebitNoteSerializer(CreditDebitNote.objects.filter(tenant=request.tenant).order_by("-created_at")[:200], many=True).data)

    def post(self, request):
        if not finance_role(request):
            return Response({"error": {"code": "PERMISSION_DENIED", "message": "Finance role required"}}, status=403)
        serializer = CreditDebitNoteSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)
        data = serializer.validated_data
        if bool(data.get("invoice")) == bool(data.get("grn")):
            return Response({"error": {"code": "VALIDATION_ERROR", "message": "Choose exactly one related invoice or GRN"}}, status=400)
        if data.get("invoice") and data["invoice"].tenant_id != request.tenant.id or data.get("grn") and data["grn"].tenant_id != request.tenant.id:
            return Response({"error": {"code": "NOT_FOUND", "message": "Related record not found"}}, status=404)
        note = CreditDebitNote.objects.create(tenant=request.tenant, created_by=request.user, **data)
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="FINANCIAL_NOTE_CREATED", object_type="CreditDebitNote", object_id=str(note.id), metadata={"kind": note.kind, "amount": str(note.amount)})
        return Response(CreditDebitNoteSerializer(note).data, status=201)


class CreditDebitNoteDecision(APIView):
    permission_classes = [HasTenantMembership]

    @transaction.atomic
    def post(self, request, note_id):
        if not finance_role(request):
            return Response({"error": {"code": "PERMISSION_DENIED", "message": "Finance role required"}}, status=403)
        note = get_object_or_404(CreditDebitNote.objects.select_for_update(), id=note_id, tenant=request.tenant)
        if note.invoice_id:
            note.invoice = get_object_or_404(Invoice.objects.select_for_update(), pk=note.invoice_id, tenant=request.tenant)
        if note.status != CreditDebitNote.Status.PENDING:
            return Response({"error": {"code": "STATE_CONFLICT", "message": "Note has already been decided"}}, status=409)
        decision = request.data.get("decision")
        if decision not in (CreditDebitNote.Status.APPROVED, CreditDebitNote.Status.REJECTED):
            return Response({"error": {"code": "VALIDATION_ERROR", "message": "decision must be APPROVED or REJECTED"}}, status=400)
        if note.created_by_id == request.user.id:
            return Response({"error": {"code": "PERMISSION_DENIED", "message": "Maker cannot approve their own financial note"}}, status=403)
        already_paid = allocated_total(note.invoice) if note.invoice_id else Decimal("0")
        if decision == CreditDebitNote.Status.APPROVED and note.invoice_id and note.kind == CreditDebitNote.Kind.CREDIT:
            if already_paid > invoice_net_payable(note.invoice) - note.amount:
                return Response({"error": {"code": "STATE_CONFLICT", "message": "Credit note would reduce payable below payments already allocated"}}, status=409)
        note.status = decision
        note.approved_by = request.user
        note.approved_at = timezone.now()
        note.save(update_fields=["status", "approved_by", "approved_at"])
        if note.invoice_id and decision == CreditDebitNote.Status.APPROVED:
            note.invoice.payment_status = "PAID" if already_paid >= invoice_net_payable(note.invoice) else "PARTIALLY_PAID" if already_paid else "UNPAID"
            note.invoice.save(update_fields=["payment_status", "updated_at"])
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action=f"FINANCIAL_NOTE_{decision}", object_type="CreditDebitNote", object_id=str(note.id), metadata={})
        return Response(CreditDebitNoteSerializer(note).data)
