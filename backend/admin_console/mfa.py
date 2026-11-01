"""Shared staff MFA policy and JWT assurance, independent of login surface."""
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from rest_framework_simplejwt.tokens import RefreshToken

from .models import AdminStaff
from .totp import decrypt_secret


MFA_SESSION_SECONDS = 24 * 60 * 60


def requires_mfa(staff):
    return bool(staff.mfa_enabled or staff.mfa_enforced or staff.role in {
        AdminStaff.Role.SUPER_ADMIN, AdminStaff.Role.BILLING_ADMIN,
    })


def credential_fingerprint(staff):
    return salted_hmac("kriyopay.admin.mfa.credentials",
                       f"{staff.user.password}:{decrypt_secret(staff.mfa_secret)}", algorithm="sha256").hexdigest()


def verified_session(staff, token):
    if not token or not hasattr(token, "get") or not staff.mfa_enabled or not decrypt_secret(staff.mfa_secret):
        return False
    verified_at = token.get("admin_mfa_at")
    if type(verified_at) is not int or not 0 <= timezone.now().timestamp() - verified_at < MFA_SESSION_SECONDS:
        return False
    return (token.get("admin_staff_id") == str(staff.pk)
            and constant_time_compare(str(token.get("admin_mfa_credentials", "")), credential_fingerprint(staff)))


def verified_tokens(staff):
    """Call only after successful MFA; refresh retains the original assurance time."""
    refresh = RefreshToken.for_user(staff.user)
    refresh["admin_staff_id"] = str(staff.pk)
    refresh["admin_mfa_at"] = int(timezone.now().timestamp())
    refresh["admin_mfa_credentials"] = credential_fingerprint(staff)
    return {"access": str(refresh.access_token), "refresh": str(refresh),
            "role": staff.role, "mfa_required": False, "mfa_verified": True}
