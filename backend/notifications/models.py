import uuid
from django.db import models
from tenants.models import Tenant
from accounts.models import User

class Notification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    channel = models.CharField(max_length=20, default="EMAIL")
    status = models.CharField(max_length=20, default="PENDING")
    payload = models.JSONField(default=dict)
    recipient = models.ForeignKey(User, null=True, on_delete=models.CASCADE, related_name="kriyopay_notifications")
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class NotificationPreference(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    preferences = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "user"], name="uniq_notification_preference_user")]
