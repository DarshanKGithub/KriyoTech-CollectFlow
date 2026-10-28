import uuid
from django.db import models
from tenants.models import Tenant
from accounts.models import User

class Vendor(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    gstin = models.CharField(max_length=15, blank=True)
    external_code = models.CharField(max_length=80, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=20, blank=True, db_index=True)
    email_domains = models.JSONField(default=list, blank=True)
    payment_terms_days = models.PositiveSmallIntegerField(default=0)
    approved = models.BooleanField(default=False)
    class Meta:
        indexes = [models.Index(fields=["tenant", "name"])]

class VendorAlias(models.Model):
    class Kind(models.TextChoices): NAME = "NAME"; EMAIL_DOMAIN = "EMAIL_DOMAIN"; GSTIN = "GSTIN"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="vendor_aliases")
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="aliases")
    alias = models.CharField(max_length=255)
    normalized_alias = models.CharField(max_length=255)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.NAME)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "normalized_alias", "kind"], name="uniq_tenant_vendor_alias")]
        indexes = [models.Index(fields=["tenant", "normalized_alias"])]
