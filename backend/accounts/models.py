import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models
from tenants.models import Tenant, Branch

class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

class Membership(models.Model):
    class Role(models.TextChoices):
        OWNER = "OWNER"; FINANCE = "FINANCE"; PURCHASE = "PURCHASE"; STORE = "STORE"; APPROVER = "APPROVER"; AUDITOR = "AUDITOR"; DRIVER = "DRIVER"; FLEET = "FLEET"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=20, choices=Role.choices)
    is_active = models.BooleanField(default=True)
    branch_scope_enabled = models.BooleanField(default=False)
    class Meta: constraints = [models.UniqueConstraint(fields=["tenant", "user"], name="uniq_membership_tenant_user")]


class BranchMembership(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    membership = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="branch_assignments")
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="membership_assignments")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["membership", "branch"], name="uniq_membership_branch")]
        indexes = [models.Index(fields=["membership", "is_active"])]

class Invitation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    email = models.EmailField()
    role = models.CharField(max_length=20, choices=Membership.Role.choices)
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    invited_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
