import uuid
from django.db import models
from tenants.models import Tenant

class EmailIngestionLog(models.Model):
    class Status(models.TextChoices): RECEIVED = "RECEIVED"; PROCESSING = "PROCESSING"; PROCESSED = "PROCESSED"; PARTIAL = "PARTIAL"; FAILED = "FAILED"; QUARANTINED = "QUARANTINED"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="email_ingestion_logs")
    provider = models.CharField(max_length=40, default="WEBHOOK")
    message_id = models.CharField(max_length=255)
    sender = models.EmailField(blank=True)
    recipient = models.EmailField(blank=True)
    subject = models.CharField(max_length=500, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RECEIVED, db_index=True)
    attachment_results = models.JSONField(default=list)
    error = models.TextField(blank=True)
    retry_count = models.PositiveSmallIntegerField(default=0)
    claimed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    processing_token = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "provider", "message_id"], name="uniq_email_ingestion_message")]
        indexes = [models.Index(fields=["tenant", "status", "created_at"])]
