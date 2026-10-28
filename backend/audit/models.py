import uuid
from django.db import models
from tenants.models import Tenant
from accounts.models import User

class AuditLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    actor = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=80)
    object_type = models.CharField(max_length=80)
    object_id = models.CharField(max_length=80)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    def save(self, *args, **kwargs):
        if not self._state.adding: raise ValueError("Audit records are immutable")
        return super().save(*args, **kwargs)
    def delete(self, *args, **kwargs): raise ValueError("Audit records are immutable")
