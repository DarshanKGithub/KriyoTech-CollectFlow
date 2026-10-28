import uuid
from django.db import models
from tenants.models import Tenant
from invoices.models import Invoice

class MatchingSetting(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name="matching_settings")
    rate_tolerance_percent = models.DecimalField(max_digits=7, decimal_places=3, default=0)
    rate_tolerance_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    quantity_tolerance_percent = models.DecimalField(max_digits=7, decimal_places=3, default=0)
    quantity_tolerance_amount = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    over_receipt_tolerance_percent = models.DecimalField(max_digits=7, decimal_places=3, default=0)
    tax_tolerance_percent = models.DecimalField(max_digits=7, decimal_places=3, default=0)
    matching_priority = models.JSONField(default=list)
    allow_partial_grn = models.BooleanField(default=True)
    require_service_acceptance = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

class MatchResult(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    invoice = models.ForeignKey(Invoice, related_name="match_results", on_delete=models.CASCADE)
    run_number = models.PositiveIntegerField()
    outcome = models.CharField(max_length=20)
    details = models.JSONField(default=dict)
    rules_version = models.CharField(max_length=30, default="1")
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: constraints = [models.UniqueConstraint(fields=["tenant", "invoice", "run_number"], name="uniq_match_run")]
