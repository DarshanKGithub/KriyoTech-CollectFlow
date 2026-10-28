from django.contrib.auth.hashers import check_password
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from .models import TenantAPIKey


class TenantAPIKeyAuthentication(BaseAuthentication):
    """Bearer authentication for the explicitly exposed, read-only external API."""
    keyword = "Bearer "

    def authenticate(self, request):
        header = request.headers.get("Authorization", "")
        if not header.startswith(self.keyword): return None
        token = header[len(self.keyword):].strip()
        parts = token.split("_", 3)
        if len(parts) != 4 or parts[0:2] != ["kp", "live"]: return None
        prefix = "kp_live_" + parts[2]
        key = TenantAPIKey.objects.select_related("tenant", "created_by").filter(prefix=prefix, revoked_at__isnull=True).first()
        if not key or not check_password(token, key.secret_hash): raise AuthenticationFailed("Invalid or revoked API key")
        if not key.created_by_id or not key.created_by.is_active: raise AuthenticationFailed("API key owner is inactive")
        key.last_used_at = timezone.now(); key.save(update_fields=["last_used_at"])
        return key.created_by, key

    def authenticate_header(self, request):
        return "Bearer"
