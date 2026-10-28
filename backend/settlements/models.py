import uuid
from django.conf import settings
from django.db import models
from .storage import FinancialSourceStorage

CURRENCIES = [(code, code) for code in ("INR", "USD", "EUR", "GBP", "AED", "SGD", "AUD", "CAD")]


class SourceAccount(models.Model):
    class Scope(models.TextChoices):
        PLATFORM = "PLATFORM", "Platform billing"
        TENANT = "TENANT", "Client workspace"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scope = models.CharField(max_length=8, choices=Scope.choices)
    tenant = models.ForeignKey("tenants.Tenant", null=True, blank=True, on_delete=models.PROTECT)
    name = models.CharField(max_length=100)
    kind = models.CharField(max_length=8, choices=[("BANK", "Bank"), ("GATEWAY", "Gateway")])
    provider = models.CharField(max_length=20, choices=[("BANK", "Bank"), ("RAZORPAY", "Razorpay"), ("OTHER", "Other")])
    external_reference = models.CharField(max_length=100)
    currency = models.CharField(max_length=3, choices=CURRENCIES)
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    # No credentials or provider API execution in the import-only release.
    class Meta:
        constraints = [
            models.CheckConstraint(condition=(models.Q(scope="PLATFORM", tenant__isnull=True) |
                                              models.Q(scope="TENANT", tenant__isnull=False)), name="settlement_account_owner"),
            models.UniqueConstraint(fields=["tenant", "kind", "provider", "external_reference", "currency"],
                                    condition=models.Q(scope="TENANT"), name="uniq_client_source_account"),
            models.UniqueConstraint(fields=["kind", "provider", "external_reference", "currency"],
                                    condition=models.Q(scope="PLATFORM"), name="uniq_platform_source_account"),
        ]


def original_path(instance, filename):
    extension = filename.rsplit(".", 1)[-1].lower()
    return f"settlements/{instance.account_id}/{instance.id}/source.{extension}"


class ImportBatch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(SourceAccount, on_delete=models.PROTECT, related_name="imports")
    filename = models.CharField(max_length=180)
    content_hash = models.CharField(max_length=64)
    original_file = models.FileField(upload_to=original_path, storage=FinancialSourceStorage())
    status = models.CharField(max_length=16, default="NEEDS_REVIEW",
        choices=[(s, s) for s in ("NEEDS_REVIEW", "INVALID", "APPROVED", "REJECTED")])
    row_count = models.PositiveIntegerField(default=0)
    errors = models.JSONField(default=list)
    warnings = models.JSONField(default=list)
    imported_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    review_note = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["account", "content_hash"], name="uniq_settlement_source_file")]


class ImportRow(models.Model):
    batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name="rows")
    row_number = models.PositiveIntegerField()
    normalized = models.JSONField()
    fingerprint = models.CharField(max_length=64)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["batch", "row_number"], name="uniq_settlement_batch_row")]


class SettlementRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(SourceAccount, on_delete=models.PROTECT, related_name="records")
    source_row = models.ForeignKey(ImportRow, on_delete=models.PROTECT)
    record_type = models.CharField(max_length=12, choices=[(s, s) for s in ("SETTLEMENT", "REFUND", "REVERSAL")])
    external_id = models.CharField(max_length=120)
    settlement_reference = models.CharField(max_length=120, blank=True)
    payment_reference = models.CharField(max_length=120, blank=True)
    currency = models.CharField(max_length=3, choices=CURRENCIES)
    gross = models.DecimalField(max_digits=18, decimal_places=2, null=True)
    fees = models.DecimalField(max_digits=18, decimal_places=2, null=True)
    fee_tax = models.DecimalField(max_digits=18, decimal_places=2, null=True)
    refunds = models.DecimalField(max_digits=18, decimal_places=2, null=True)
    adjustments = models.DecimalField(max_digits=18, decimal_places=2, null=True)
    net = models.DecimalField(max_digits=18, decimal_places=2, null=True)
    amount = models.DecimalField(max_digits=18, decimal_places=2, null=True)
    expected_date = models.DateField(null=True)
    settled_date = models.DateField(null=True)
    reverses = models.OneToOneField("self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversed_by")
    fingerprint = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["account", "record_type", "external_id"], name="uniq_observed_provider_record")]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Source observations are immutable; import a reversal/correction.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Source observations are immutable.")
