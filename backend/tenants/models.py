import uuid
from django.db import models

class Tenant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    workspace_key = models.SlugField(max_length=80, unique=True)
    settings = models.JSONField(default=dict, blank=True)
    invoice_intake_token = models.CharField(max_length=64, unique=True, null=True, blank=True, default=None)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return self.name


class Branch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="branches")
    name = models.CharField(max_length=120)
    code = models.SlugField(max_length=80)
    active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "code"], name="uniq_tenant_branch_code"),
            models.UniqueConstraint(fields=["tenant"], condition=models.Q(is_default=True), name="uniq_tenant_default_branch"),
        ]
        indexes = [models.Index(fields=["tenant", "active", "name"])]

    def __str__(self): return f"{self.tenant.name} · {self.name}"


def default_branch_for(tenant_id):
    branch, _ = Branch.objects.get_or_create(
        tenant_id=tenant_id,
        code="main",
        defaults={"name": "Main branch", "active": True, "is_default": True},
    )
    if not branch.is_default:
        branch.is_default = True
        branch.save(update_fields=["is_default"])
    return branch
