import uuid
from django.db import models
from tenants.models import Tenant
from accounts.models import User

def tenant_document_path(instance, filename):
    from partners.context import current_schema
    prefix = "" if current_schema() == "public" else f"resellers/{current_schema()}/"
    return f"{prefix}{instance.tenant_id}/{instance.id}/{filename}"

class Document(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    file = models.FileField(upload_to=tenant_document_path, max_length=512)
    filename = models.CharField(max_length=255)
    media_type = models.CharField(max_length=100)
    checksum_sha256 = models.CharField(max_length=64, db_index=True)
    size_bytes = models.PositiveBigIntegerField()
    uploaded_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
