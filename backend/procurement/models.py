import uuid
from django.db import models
from tenants.models import Tenant
from vendors.models import Vendor

class PurchaseOrder(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT"; PENDING_APPROVAL = "PENDING_APPROVAL"; APPROVED = "APPROVED"; CANCELLED = "CANCELLED"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT)
    number = models.CharField(max_length=100)
    order_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    revision = models.PositiveIntegerField(default=1)
    approved_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="approved_purchase_orders")
    approved_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "number"], name="uniq_tenant_po_number")]
        indexes = [models.Index(fields=["tenant", "number"])]

class PurchaseOrderLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    purchase_order = models.ForeignKey(PurchaseOrder, related_name="lines", on_delete=models.CASCADE)
    line_no = models.PositiveIntegerField()
    item_code = models.CharField(max_length=100, blank=True)
    description = models.CharField(max_length=255)
    hsn_sac = models.CharField(max_length=20, blank=True)
    quantity = models.DecimalField(max_digits=18, decimal_places=6)
    uom = models.CharField(max_length=30, blank=True)
    rate = models.DecimalField(max_digits=18, decimal_places=6)
    taxable_value = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    gst_rate = models.DecimalField(max_digits=6, decimal_places=3, default=0)

class PurchaseOrderRevision(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="purchase_order_revisions")
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="revisions")
    revision = models.PositiveIntegerField()
    action = models.CharField(max_length=20, default="EDITED")
    change_note = models.CharField(max_length=500, blank=True)
    snapshot = models.JSONField(default=dict)
    changed_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["purchase_order", "revision"], name="uniq_po_revision_number")]
        indexes = [models.Index(fields=["tenant", "purchase_order", "created_at"])]

class GRN(models.Model):
    class QualityStatus(models.TextChoices):
        PENDING = "PENDING"; ACCEPTED = "ACCEPTED"; PARTIAL = "PARTIAL"; REJECTED = "REJECTED"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT)
    purchase_order = models.ForeignKey(PurchaseOrder, null=True, blank=True, on_delete=models.PROTECT)
    number = models.CharField(max_length=100)
    received_at = models.DateField(null=True, blank=True)
    service_accepted = models.BooleanField(default=False)
    service_acceptance_reference = models.CharField(max_length=255, blank=True)
    quality_status = models.CharField(max_length=12, choices=QualityStatus.choices, default=QualityStatus.PENDING)
    quality_note = models.TextField(blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "number"], name="uniq_tenant_grn_number")]
        indexes = [models.Index(fields=["tenant", "number"])]

class GRNLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    grn = models.ForeignKey(GRN, related_name="lines", on_delete=models.CASCADE)
    purchase_order_line = models.ForeignKey(PurchaseOrderLine, null=True, blank=True, on_delete=models.PROTECT)
    description = models.CharField(max_length=255)
    item_code = models.CharField(max_length=100, blank=True)
    quantity_received = models.DecimalField(max_digits=18, decimal_places=6)
    uom = models.CharField(max_length=30, blank=True)
