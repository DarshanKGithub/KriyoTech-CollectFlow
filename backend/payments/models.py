import uuid
from django.db import models
from tenants.models import Tenant
from accounts.models import User
from invoices.models import Invoice
from procurement.models import GRN

class Payment(models.Model):
    class Mode(models.TextChoices): BANK_TRANSFER = "BANK_TRANSFER"; UPI = "UPI"; CHEQUE = "CHEQUE"; CASH = "CASH"; OTHER = "OTHER"
    source_account = models.ForeignKey("settlements.SourceAccount", null=True, blank=True, on_delete=models.PROTECT)
    currency = models.CharField(max_length=3, blank=True, default="")
    provenance_note = models.CharField(max_length=500, blank=True)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="payments")
    vendor = models.ForeignKey("vendors.Vendor", null=True, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    reference_number = models.CharField(max_length=120, blank=True)
    idempotency_key = models.UUIDField(null=True, blank=True)
    mode = models.CharField(max_length=20, choices=Mode.choices, default=Mode.BANK_TRANSFER)
    paid_at = models.DateField()
    remarks = models.TextField(blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0), name="payment_amount_positive"), models.UniqueConstraint(fields=["tenant", "idempotency_key"], condition=models.Q(idempotency_key__isnull=False), name="uniq_payment_idempotency")]
        indexes = [models.Index(fields=["tenant", "paid_at"]), models.Index(fields=["tenant", "vendor", "paid_at"])]

class PaymentAllocation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="allocations")
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="payment_allocations")
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0), name="allocation_amount_positive")]
        indexes = [models.Index(fields=["tenant", "invoice"])]


class PayoutInstruction(models.Model):
    """A maker-checker request for a future provider payout; never a payment ledger entry."""
    class Status(models.TextChoices):
        AWAITING_APPROVAL = "AWAITING_APPROVAL", "Awaiting approval"
        APPROVED = "APPROVED", "Approved for provider"
        REJECTED = "REJECTED", "Rejected"
        CANCELLED = "CANCELLED", "Cancelled"
        STALE = "STALE", "Balance changed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="payout_instructions")
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="payout_instructions")
    vendor = models.ForeignKey("vendors.Vendor", on_delete=models.PROTECT, related_name="payout_instructions")
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    currency = models.CharField(max_length=3, default="INR")
    idempotency_key = models.UUIDField()
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.AWAITING_APPROVAL, db_index=True)
    requested_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="requested_payout_instructions")
    reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_payout_instructions")
    review_note = models.CharField(max_length=1000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="payout_instruction_amount_positive"),
            models.UniqueConstraint(fields=["tenant", "idempotency_key"], name="uniq_payout_instruction_idempotency"),
        ]
        indexes = [models.Index(fields=["tenant", "status", "created_at"])]

class CreditDebitNote(models.Model):
    class Kind(models.TextChoices): CREDIT = "CREDIT"; DEBIT = "DEBIT"
    class Reason(models.TextChoices): QUANTITY_SHORTAGE = "QUANTITY_SHORTAGE"; DAMAGED_GOODS = "DAMAGED_GOODS"; RATE_CORRECTION = "RATE_CORRECTION"; DISCOUNT = "DISCOUNT"; RETURN = "RETURN"; TAX_CORRECTION = "TAX_CORRECTION"; OTHER = "OTHER"
    class Status(models.TextChoices): PENDING = "PENDING"; APPROVED = "APPROVED"; REJECTED = "REJECTED"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="credit_debit_notes")
    kind = models.CharField(max_length=8, choices=Kind.choices)
    invoice = models.ForeignKey(Invoice, null=True, blank=True, on_delete=models.PROTECT, related_name="credit_debit_notes")
    grn = models.ForeignKey(GRN, null=True, blank=True, on_delete=models.PROTECT, related_name="credit_debit_notes")
    note_number = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    reason = models.CharField(max_length=30, choices=Reason.choices)
    remarks = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="created_financial_notes")
    approved_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="approved_financial_notes")
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0), name="note_amount_positive"), models.UniqueConstraint(fields=["tenant", "kind", "note_number"], name="uniq_note_number_per_tenant")]
        indexes = [models.Index(fields=["tenant", "status"])]
