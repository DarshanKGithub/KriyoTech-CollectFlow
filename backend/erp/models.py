import uuid
from django.conf import settings
from django.db import models


class ERPConnection(models.Model):
    class Provider(models.TextChoices):
        DYNAMICS_FINANCE = "DYNAMICS_FINANCE", "Microsoft Dynamics 365 Finance"
        ERPNEXT = "ERPNEXT", "ERPNext"
        TALLY = "TALLY", "TallyPrime"
        ZOHO_BOOKS = "ZOHO_BOOKS", "Zoho Books"
        ZOHO_INVENTORY = "ZOHO_INVENTORY", "Zoho Inventory"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE)
    provider = models.CharField(max_length=24, choices=Provider.choices)
    name = models.CharField(max_length=120)
    config = models.JSONField(default=dict)
    encrypted_credentials = models.TextField(blank=True)
    enabled = models.BooleanField(default=False)
    tested_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class ERPSyncRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    connection = models.ForeignKey(ERPConnection, on_delete=models.CASCADE, related_name="runs")
    resource = models.CharField(max_length=24)
    direction = models.CharField(max_length=8, default="INBOUND")
    status = models.CharField(max_length=24, default="QUEUED", db_index=True)
    record_count = models.PositiveIntegerField(default=0)
    page = models.PositiveIntegerField(default=1)
    has_more = models.BooleanField(default=False)
    error = models.CharField(max_length=300, blank=True)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)


class ERPRecord(models.Model):
    """Reviewable inbox/outbox. Remote writes with ambiguous outcomes are fenced."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    connection = models.ForeignKey(ERPConnection, on_delete=models.CASCADE, related_name="records")
    resource = models.CharField(max_length=24)
    direction = models.CharField(max_length=8, default="INBOUND")
    external_id = models.CharField(max_length=200, blank=True)
    local_id = models.UUIDField(null=True, blank=True)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=24, default="NEEDS_REVIEW", db_index=True)
    error = models.CharField(max_length=300, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["connection", "resource", "external_id"], condition=models.Q(direction="INBOUND"), name="uniq_erp_inbound_record"),
            models.UniqueConstraint(fields=["connection", "resource", "local_id"], condition=models.Q(direction="OUTBOUND"), name="uniq_erp_outbound_record"),
        ]
        indexes = [models.Index(fields=["connection", "direction", "status"])]
