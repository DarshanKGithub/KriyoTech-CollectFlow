from decimal import Decimal, InvalidOperation
from django.db import IntegrityError, transaction
from django.db.models import Sum, OuterRef, Subquery, Value, F, DecimalField
from django.db.models.functions import Coalesce, Greatest
from rest_framework.exceptions import APIException, ValidationError
from audit.models import AuditLog
from invoices.models import Invoice
from vendors.models import Vendor
from .models import CreditDebitNote, Payment, PaymentAllocation


class PaymentConflict(APIException):
    status_code = 409
    default_code = "STATE_CONFLICT"
    default_detail = "This payment conflicts with the current invoice balance or workflow."


def with_invoice_balances(queryset):
    """Exact ledger policy for dashboards/reports, without per-invoice queries."""
    field = DecimalField(max_digits=18, decimal_places=2)
    zero = Value(Decimal("0"), output_field=field)
    notes = CreditDebitNote.objects.filter(tenant_id=OuterRef("tenant_id"), invoice_id=OuterRef("pk"),
                                          status="APPROVED").order_by().values("invoice_id")
    def total(rows):
        return Coalesce(Subquery(rows.annotate(total=Sum("amount")).values("total")[:1], output_field=field), zero)
    paid = PaymentAllocation.objects.filter(tenant_id=OuterRef("tenant_id"), invoice_id=OuterRef("pk"),
                                            payment__cancelled_at__isnull=True).order_by().values("invoice_id")
    return queryset.annotate(
        ledger_credits=total(notes.filter(kind="CREDIT")), ledger_debits=total(notes.filter(kind="DEBIT")),
        ledger_paid=total(paid),
    ).annotate(ledger_payable=Greatest(F("invoice_total")-F("ledger_credits")+F("ledger_debits"), zero)
    ).annotate(outstanding_balance=Greatest(F("ledger_payable")-F("ledger_paid"), zero))


def invoice_net_payable(invoice):
    notes = invoice.credit_debit_notes.filter(status="APPROVED")
    credits = notes.filter(kind=CreditDebitNote.Kind.CREDIT).aggregate(total=Sum("amount"))["total"] or Decimal(0)
    debits = notes.filter(kind=CreditDebitNote.Kind.DEBIT).aggregate(total=Sum("amount"))["total"] or Decimal(0)
    return max(invoice.invoice_total-credits+debits, Decimal(0))


def allocated_total(invoice):
    return invoice.payment_allocations.filter(payment__cancelled_at__isnull=True).aggregate(total=Sum("amount"))["total"] or Decimal(0)


def money(value):
    try:
        value = Decimal(str(value))
        if not value.is_finite() or value <= 0 or value > Decimal("9999999999999999.99") or value != value.quantize(Decimal("0.01")):
            raise ValueError()
        return value
    except (ValueError, TypeError, InvalidOperation):
        raise ValidationError({"amount": "Enter a positive amount with at most two decimal places."}) from None


def _replay(existing, data, grouped, vendor):
    existing_allocations = {}
    for allocation in existing.allocations.all():
        key = str(allocation.invoice_id)
        existing_allocations[key] = existing_allocations.get(key, Decimal(0))+allocation.amount
    same = (existing.vendor_id == vendor.pk and existing.amount == data["amount"]
            and existing.paid_at == data["paid_at"] and existing.mode == data.get("mode", Payment.Mode.BANK_TRANSFER)
            and existing.reference_number == data.get("reference_number", "")
            and existing.remarks == data.get("remarks", "") and existing_allocations == grouped)
    if not same or existing.cancelled_at:
        raise PaymentConflict("This request key belongs to a different or cancelled payment. Use a new key for a new payment.")
    return existing, False


@transaction.atomic
def record_payment(*, tenant, actor, data, allocations):
    """Shared manual/ERP balance check and write, serialized by invoice locks."""
    data = dict(data)
    data["amount"] = money(data.get("amount"))
    if not allocations:
        raise ValidationError({"allocations": "At least one invoice allocation is required."})
    grouped = {}
    for allocation in allocations:
        invoice = allocation["invoice"]
        key = str(invoice.pk)
        if invoice.tenant_id != tenant.pk:
            raise ValidationError({"allocations": "Invoices must belong to this workspace."})
        grouped[key] = grouped.get(key, Decimal(0))+money(allocation["amount"])
    if sum(grouped.values()) != data["amount"]:
        raise ValidationError({"allocations": "Payment amount must equal the allocated amount."})
    # All writers take these locks in the same order. This includes ERP imports.
    invoices = list(Invoice.objects.select_for_update(of=("self",)).filter(tenant=tenant, pk__in=sorted(grouped)).order_by("pk"))
    if len(invoices) != len(grouped):
        raise ValidationError({"allocations": "An invoice is no longer available in this workspace."})
    vendor_ids = {invoice.vendor_id for invoice in invoices}
    if None in vendor_ids:
        raise ValidationError({"vendor": "This invoice has no linked supplier. Select the correct supplier and send the invoice through review and approval again."})
    if len(vendor_ids) != 1:
        raise ValidationError({"vendor": "All invoices must have the same workspace supplier."})
    vendor = data.get("vendor")
    if vendor is None:
        vendor = Vendor.objects.get(tenant=tenant, pk=next(iter(vendor_ids)))
    if vendor.tenant_id != tenant.pk or vendor.pk != next(iter(vendor_ids)):
        raise ValidationError({"vendor": "Supplier must match the invoices and current workspace."})
    data["vendor"] = vendor
    key = data.get("idempotency_key")
    if key:
        existing = Payment.objects.filter(tenant=tenant, idempotency_key=key).first()
        if existing:
            return _replay(existing, data, grouped, vendor)
    if not vendor.approved:
        raise PaymentConflict("The supplier must be approved before recording a payment.")
    for invoice in invoices:
        if invoice.status not in {Invoice.Status.PAYMENT_READY, Invoice.Status.EXPORTED} or invoice.payment_status == "CANCELLED":
            raise PaymentConflict("Every invoice must be approved and payment ready before recording payment.")
        if invoice.exceptions.filter(blocking=True).exclude(status__in=["RESOLVED", "OVERRIDDEN"]).exists():
            raise PaymentConflict("Resolve blocking invoice exceptions before recording payment.")
        if grouped[str(invoice.pk)]+allocated_total(invoice) > invoice_net_payable(invoice):
            raise PaymentConflict(f"Allocation exceeds the outstanding balance for invoice {invoice.invoice_number}.")
    try:
        # Isolate the unique-key race in a savepoint so the winning payment can
        # be read after a concurrent insert without a broken DB transaction.
        with transaction.atomic():
            payment = Payment.objects.create(tenant=tenant, created_by=actor, **data)
            for invoice in invoices:
                PaymentAllocation.objects.create(tenant=tenant, payment=payment, invoice=invoice, amount=grouped[str(invoice.pk)])
            for invoice in invoices:
                paid = allocated_total(invoice)
                invoice.payment_status = "PAID" if paid >= invoice_net_payable(invoice) else "PARTIALLY_PAID"
                invoice.save(update_fields=["payment_status", "updated_at"])
            AuditLog.objects.create(tenant=tenant, actor=actor, action="PAYMENT_RECORDED", object_type="Payment", object_id=str(payment.pk), metadata={"amount": str(payment.amount), "allocations": len(grouped)})
    except IntegrityError:
        existing = Payment.objects.filter(tenant=tenant, idempotency_key=key).first() if key else None
        if existing:
            return _replay(existing, data, grouped, vendor)
        raise
    return payment, True
