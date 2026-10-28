import uuid

from django.db import models

from accounts.models import User
from tenants.models import Tenant


class BulkJob(models.Model):
    class Status(models.TextChoices): PREVIEW = "PREVIEW"; COMMITTED = "COMMITTED"; COMPLETED = "COMPLETED"; FAILED = "FAILED"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="bulk_jobs")
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    operation = models.CharField(max_length=40)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PREVIEW)
    target_ids = models.JSONField(default=list)
    preview = models.JSONField(default=dict)
    preview_token = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    result = models.JSONField(default=dict)
    committed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        indexes = [models.Index(fields=["tenant", "status", "created_at"])]
