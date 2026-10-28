import uuid
from django.db import models
from tenants.models import Tenant
from accounts.models import User

def tenant_document_path(instance, filename): return f"{instance.tenant_id}/{instance.id}/{filename}"

class Document(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    file = models.FileField(upload_to=tenant_document_path)
    filename = models.CharField(max_length=255)
    media_type = models.CharField(max_length=100)
    checksum_sha256 = models.CharField(max_length=64, db_index=True)
    size_bytes = models.PositiveBigIntegerField()
    uploaded_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
