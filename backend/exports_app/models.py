import uuid
from django.db import models
from tenants.models import Tenant
from accounts.models import User

class ExportJob(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    requested_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=20, default="PENDING")
    format = models.CharField(max_length=20, default="TALLY_CSV")
    row_count = models.PositiveIntegerField(default=0)
    debit_total = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    credit_total = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)


class TallyLedgerMapping(models.Model):
    class Dimension(models.TextChoices):
        VENDOR_LEDGER = "VENDOR_LEDGER"; PURCHASE_LEDGER = "PURCHASE_LEDGER"; GST_LEDGER = "GST_LEDGER"; TDS_LEDGER = "TDS_LEDGER"; COST_CENTER = "COST_CENTER"; VOUCHER_TYPE = "VOUCHER_TYPE"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="tally_ledger_mappings")
    dimension = models.CharField(max_length=24, choices=Dimension.choices)
    source_key = models.CharField(max_length=120)
    ledger_name = models.CharField(max_length=120)
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="created_tally_mappings")
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "dimension", "source_key"], name="uniq_tally_mapping_source")]
        indexes = [models.Index(fields=["tenant", "dimension", "active"])]
