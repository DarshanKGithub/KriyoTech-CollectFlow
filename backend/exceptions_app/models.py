import uuid
from django.db import models
from tenants.models import Tenant
from accounts.models import User
from invoices.models import Invoice
from matching.models import MatchResult

class InvoiceException(models.Model):
    class Status(models.TextChoices): OPEN = "OPEN"; ASSIGNED = "ASSIGNED"; RESOLVED = "RESOLVED"; OVERRIDDEN = "OVERRIDDEN"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    invoice = models.ForeignKey(Invoice, related_name="exceptions", on_delete=models.CASCADE)
    match_result = models.ForeignKey(MatchResult, null=True, on_delete=models.SET_NULL)
    code = models.CharField(max_length=40)
    severity = models.CharField(max_length=20, default="HIGH")
    priority = models.CharField(max_length=12, default="HIGH", choices=[("LOW", "Low"), ("MEDIUM", "Medium"), ("HIGH", "High"), ("CRITICAL", "Critical")])
    blocking = models.BooleanField(default=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True)
    assigned_to = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    details = models.JSONField(default=dict)
    resolution_note = models.TextField(blank=True)
    override_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    sla_due_at = models.DateTimeField(null=True, blank=True, db_index=True)
    escalation_level = models.PositiveSmallIntegerField(default=0)

class ExceptionSLA(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="exception_slas")
    exception_code = models.CharField(max_length=40)
    due_after_hours = models.PositiveIntegerField(default=48)
    priority = models.CharField(max_length=12, default="MEDIUM", choices=[("LOW", "Low"), ("MEDIUM", "Medium"), ("HIGH", "High"), ("CRITICAL", "Critical")])
    escalation_roles = models.JSONField(default=list)
    active = models.BooleanField(default=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "exception_code"], name="uniq_exception_sla_code")]

class ExceptionEscalation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    exception = models.ForeignKey(InvoiceException, on_delete=models.CASCADE, related_name="escalations")
    level = models.PositiveSmallIntegerField()
    escalated_to = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    reason = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "exception", "level"], name="uniq_exception_escalation_level")]
