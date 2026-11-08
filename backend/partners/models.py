import uuid
from django.core.validators import RegexValidator
from django.db import models


class Partner(models.Model):
    """Platform-only registry. Business and identity tables live in schema_name."""
    class Status(models.TextChoices):
        PROVISIONING = "PROVISIONING"
        ACTIVE = "ACTIVE"
        SUSPENDED = "SUSPENDED"
        FAILED = "FAILED"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=63, unique=True)
    schema_name = models.CharField(max_length=63, unique=True, editable=False)
    product_name = models.CharField(max_length=100)
    primary_color = models.CharField(max_length=7, default="#16734A", validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$")])
    support_email = models.EmailField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PROVISIONING)
    # Must be configured by platform operations after DNS/TLS verification.
    domain = models.CharField(max_length=253, blank=True, unique=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    provisioned_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.schema_name:
            self.schema_name = "partner_" + self.id.hex
        super().save(*args, **kwargs)

