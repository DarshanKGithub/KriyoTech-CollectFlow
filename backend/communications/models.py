import uuid

from django.conf import settings
from django.db import models

from tenants.models import Tenant


class WhatsAppEndpoint(models.Model):
    """Maps a Meta phone-number ID to one tenant; API credentials stay in env secrets."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="whatsapp_endpoints")
    phone_number_id = models.CharField(max_length=80, unique=True)
    display_phone_number = models.CharField(max_length=40, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


class WhatsAppMessage(models.Model):
    class Direction(models.TextChoices): INBOUND = "INBOUND"; OUTBOUND = "OUTBOUND"
    class Status(models.TextChoices): RECEIVED = "RECEIVED"; QUEUED = "QUEUED"; SENT = "SENT"; DELIVERED = "DELIVERED"; READ = "READ"; FAILED = "FAILED"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="whatsapp_messages")
    endpoint = models.ForeignKey(WhatsAppEndpoint, on_delete=models.PROTECT, related_name="messages")
    external_id = models.CharField(max_length=255)
    contact_phone = models.CharField(max_length=24, db_index=True)
    direction = models.CharField(max_length=8, choices=Direction.choices)
    message_type = models.CharField(max_length=24, default="text")
    body = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.RECEIVED, db_index=True)
    invoice = models.ForeignKey("invoices.Invoice", null=True, blank=True, on_delete=models.SET_NULL, related_name="whatsapp_messages")
    document = models.ForeignKey("documents.Document", null=True, blank=True, on_delete=models.SET_NULL, related_name="whatsapp_messages")
    metadata = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)
    sent_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    received_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "external_id"], name="uniq_whatsapp_message_id")]
        indexes = [models.Index(fields=["tenant", "contact_phone", "created_at"])]


class WhatsAppMessageDraft(models.Model):
    class Purpose(models.TextChoices): APPROVAL = "APPROVAL_REQUEST"; REMINDER = "PAYMENT_REMINDER"; CLARIFICATION = "CLARIFICATION"; OTHER = "OTHER"
    class Status(models.TextChoices): DRAFT = "DRAFT"; SENDING = "SENDING"; SENT = "SENT"; FAILED = "FAILED"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="whatsapp_message_drafts")
    invoice = models.ForeignKey("invoices.Invoice", on_delete=models.CASCADE, related_name="whatsapp_drafts")
    endpoint = models.ForeignKey(WhatsAppEndpoint, on_delete=models.PROTECT)
    recipient_phone = models.CharField(max_length=24)
    recipient_consent_confirmed = models.BooleanField(default=False)
    purpose = models.CharField(max_length=24, choices=Purpose.choices)
    body = models.TextField()
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.DRAFT, db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_whatsapp_drafts")
    sent_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="sent_whatsapp_drafts")
    message = models.OneToOneField(WhatsAppMessage, null=True, blank=True, on_delete=models.SET_NULL, related_name="draft")
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    send_started_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)


class WhatsAppConsent(models.Model):
    class Status(models.TextChoices): OPTED_IN = "OPTED_IN"; OPTED_OUT = "OPTED_OUT"
    class Source(models.TextChoices): MANUAL = "MANUAL"; INBOUND_KEYWORD = "INBOUND_KEYWORD"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="whatsapp_consents")
    vendor = models.ForeignKey("vendors.Vendor", null=True, blank=True, on_delete=models.SET_NULL, related_name="whatsapp_consents")
    phone = models.CharField(max_length=24)
    status = models.CharField(max_length=10, choices=Status.choices, db_index=True)
    source = models.CharField(max_length=20, choices=Source.choices)
    evidence_note = models.TextField(blank=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "phone"], name="uniq_tenant_whatsapp_consent_phone")]
        indexes = [models.Index(fields=["tenant", "status", "updated_at"])]
