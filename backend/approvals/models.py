import uuid
from django.db import models
from tenants.models import Tenant
from accounts.models import User
from invoices.models import Invoice

class Approval(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    invoice = models.ForeignKey(Invoice, related_name="approvals", on_delete=models.CASCADE)
    invoice_version = models.PositiveIntegerField()
    approver = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT)
    decision = models.CharField(max_length=12, choices=[("APPROVED", "Approved"), ("REJECTED", "Rejected")])
    method = models.CharField(max_length=20, default="HUMAN", choices=[("HUMAN", "Human"), ("AUTO_RULE", "Auto rule")])
    rule_evaluation = models.JSONField(default=dict, blank=True)
    comments = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    decided_at = models.DateTimeField(auto_now_add=True)

class ApprovalRule(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="approval_rules")
    name = models.CharField(max_length=160)
    priority = models.PositiveIntegerField(default=100)
    conditions = models.JSONField(default=dict)
    steps = models.JSONField(default=list)
    active = models.BooleanField(default=True, db_index=True)
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="created_approval_rules")
    updated_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="updated_approval_rules")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ["priority", "created_at"]
        indexes = [models.Index(fields=["tenant", "active", "priority"])]

class ApprovalStep(models.Model):
    class Status(models.TextChoices): PENDING = "PENDING"; APPROVED = "APPROVED"; REJECTED = "REJECTED"; SKIPPED = "SKIPPED"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="approval_steps")
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="approval_steps")
    workflow_version = models.PositiveIntegerField(default=1)
    sequence = models.PositiveSmallIntegerField()
    approver_role = models.CharField(max_length=20, blank=True)
    approver = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name="assigned_approval_steps")
    delegated_from = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="delegated_approval_steps")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    evaluation = models.JSONField(default=dict)
    comments = models.TextField(blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    due_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "invoice", "workflow_version", "sequence"], name="uniq_approval_step_sequence")]
        indexes = [models.Index(fields=["tenant", "status", "due_at"])]

class ApprovalDelegation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="approval_delegations")
    delegator = models.ForeignKey(User, on_delete=models.CASCADE, related_name="approval_delegations")
    delegate = models.ForeignKey(User, on_delete=models.CASCADE, related_name="delegated_approvals")
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(ends_at__gt=models.F("starts_at")), name="delegation_end_after_start")]
        indexes = [models.Index(fields=["tenant", "delegator", "active", "starts_at", "ends_at"])]

class AutoApprovalRule(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="auto_approval_rules")
    name = models.CharField(max_length=160)
    enabled = models.BooleanField(default=False)
    amount_limit = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    allowed_vendor_ids = models.JSONField(default=list, blank=True)
    conditions = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    updated_at = models.DateTimeField(auto_now=True)
