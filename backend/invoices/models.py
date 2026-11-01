import uuid
from django.db import models, transaction
from django.utils import timezone
from tenants.models import Tenant
from accounts.models import User
from vendors.models import Vendor
from documents.models import Document

class Invoice(models.Model):
    class Status(models.TextChoices):
        UPLOADED = "UPLOADED"; EXTRACTING = "EXTRACTING"; EXTRACTION_FAILED = "EXTRACTION_FAILED"; REVIEW_REQUIRED = "REVIEW_REQUIRED"; MATCHED = "MATCHED"; EXCEPTION = "EXCEPTION"; APPROVAL_PENDING = "APPROVAL_PENDING"; APPROVED = "APPROVED"; REJECTED = "REJECTED"; PAYMENT_READY = "PAYMENT_READY"; EXPORTED = "EXPORTED"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    vendor = models.ForeignKey(Vendor, null=True, blank=True, on_delete=models.PROTECT)
    document = models.ForeignKey(Document, null=True, blank=True, on_delete=models.PROTECT)
    supplier_name = models.CharField(max_length=200, blank=True)
    supplier_gstin = models.CharField(max_length=15, blank=True)
    invoice_number = models.CharField(max_length=100, blank=True)
    invoice_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    po_number = models.CharField(max_length=100, blank=True)
    category = models.CharField(max_length=30, default="OTHER", db_index=True)
    vendor_match_confidence = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    vendor_match_method = models.CharField(max_length=40, blank=True)
    duplicate_review_complete = models.BooleanField(default=False)
    source_email = models.JSONField(default=dict, blank=True)
    source_channel = models.CharField(max_length=24, default="MANUAL", db_index=True)
    payment_status = models.CharField(max_length=20, default="UNPAID", choices=[("UNPAID", "Unpaid"), ("PARTIALLY_PAID", "Partially paid"), ("PAID", "Paid"), ("CANCELLED", "Cancelled")], db_index=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.UPLOADED, db_index=True)
    automation = models.JSONField(default=dict, blank=True, editable=False)
    version = models.PositiveIntegerField(default=1)
    financial_locked_at = models.DateTimeField(null=True, blank=True, editable=False)
    taxable_total = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    gst_total = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    tds_total = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    invoice_total = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    uploaded_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        indexes = [models.Index(fields=["tenant", "invoice_number"]), models.Index(fields=["tenant", "vendor", "invoice_number"]), models.Index(fields=["tenant", "status"])]

    def save(self, *args, **kwargs):
        if self.financial_locked_at is None and (self.status in {"APPROVED", "PAYMENT_READY", "EXPORTED"} or self.payment_status in {"PAID", "PARTIALLY_PAID"}):
            self.financial_locked_at = timezone.now()
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = set(kwargs["update_fields"]) | {"financial_locked_at"}
        if self._state.adding and self.tenant_id:
            from .quota import enforce_invoice_quota
            with transaction.atomic():
                enforce_invoice_quota(self.tenant)
                super().save(*args, **kwargs)
            return
        super().save(*args, **kwargs)

class InvoiceLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    invoice = models.ForeignKey(Invoice, related_name="lines", on_delete=models.CASCADE)
    line_no = models.PositiveIntegerField()
    item_code = models.CharField(max_length=100, blank=True)
    description = models.CharField(max_length=255)
    hsn_sac = models.CharField(max_length=20, blank=True)
    quantity = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    uom = models.CharField(max_length=30, blank=True)
    rate = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    taxable_value = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    gst_rate = models.DecimalField(max_digits=6, decimal_places=3, default=0)
    gst_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    tds_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    class Meta: constraints = [models.UniqueConstraint(fields=["tenant", "invoice", "line_no"], name="uniq_invoice_line_no")]

class ExtractionResult(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    invoice = models.ForeignKey(Invoice, related_name="extractions", on_delete=models.CASCADE)
    provider = models.CharField(max_length=80, default="manual")
    output = models.JSONField(default=dict)
    confidence = models.JSONField(default=dict)
    status = models.CharField(max_length=30, default="COMPLETED")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    claim_token = models.UUIDField(null=True, blank=True)

class DuplicateCheck(models.Model):
    class Kind(models.TextChoices): FILE = "FILE"; EXACT = "EXACT"; NEAR = "NEAR"
    class Decision(models.TextChoices): PENDING = "PENDING"; CONFIRM_DUPLICATE = "CONFIRM_DUPLICATE"; NOT_DUPLICATE = "NOT_DUPLICATE"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="duplicate_checks")
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="duplicate_checks")
    candidate_invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="suspected_duplicates")
    kind = models.CharField(max_length=12, choices=Kind.choices)
    score = models.DecimalField(max_digits=5, decimal_places=4, default=0)
    reasons = models.JSONField(default=list)
    decision = models.CharField(max_length=24, choices=Decision.choices, default=Decision.PENDING, db_index=True)
    decision_note = models.TextField(blank=True)
    decided_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "invoice", "candidate_invoice", "kind"], name="uniq_invoice_duplicate_check")]
        indexes = [models.Index(fields=["tenant", "decision"]), models.Index(fields=["tenant", "invoice"])]

class CustomFieldDefinition(models.Model):
    class Type(models.TextChoices): TEXT = "TEXT"; NUMBER = "NUMBER"; DATE = "DATE"; BOOLEAN = "BOOLEAN"; CHOICE = "CHOICE"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="invoice_custom_fields")
    name = models.CharField(max_length=80)
    key = models.SlugField(max_length=80)
    field_type = models.CharField(max_length=12, choices=Type.choices)
    required = models.BooleanField(default=False)
    options = models.JSONField(default=list, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "key"], name="uniq_custom_field_key")]

class InvoiceCustomFieldValue(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="custom_field_values")
    definition = models.ForeignKey(CustomFieldDefinition, on_delete=models.CASCADE, related_name="values")
    value = models.JSONField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "invoice", "definition"], name="uniq_invoice_custom_field_value")]

class VendorFollowUpDraft(models.Model):
    class Status(models.TextChoices): DRAFT = "DRAFT"; READY = "READY"; SENT = "SENT"; CANCELLED = "CANCELLED"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="vendor_followups")
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="followups")
    recipient = models.EmailField(blank=True)
    subject = models.CharField(max_length=255)
    body = models.TextField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    sent_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="sent_vendor_followups")
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
