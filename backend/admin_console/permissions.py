from rest_framework.permissions import BasePermission, SAFE_METHODS
from .models import AdminStaff


class IsAdminStaff(BasePermission):
    message = "KriyoPay internal staff access is required."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        staff = AdminStaff.objects.filter(user=request.user, is_active=True).first()
        if not staff:
            self.message = "This account is not assigned an active KriyoPay internal staff role."
            from .models import AdminAuditLog
            AdminAuditLog.objects.create(actor=request.user, action="ADMIN_ACCESS_DENIED", object_type=view.__class__.__name__, metadata={"path": request.path, "method": request.method})
            return False
        request.admin_staff = staff

        # Enforce MFA for high-privilege roles
        if self._is_mfa_required_for_role(staff):
            if not self._is_mfa_completed(staff):
                self.message = "Super Admin access requires MFA. Sign in again and complete two-factor authentication."
                from .models import AdminAuditLog
                AdminAuditLog.objects.create(actor=request.user, actor_role=staff.role, action="ADMIN_MFA_REQUIRED_BUT_NOT_COMPLETED", object_type=view.__class__.__name__, metadata={"path": request.path, "method": request.method})
                return False

        allowed = getattr(view, "allowed_roles", None)
        if allowed and staff.role not in allowed:
            from .models import AdminAuditLog
            AdminAuditLog.objects.create(actor=request.user, actor_role=staff.role, action="ADMIN_PERMISSION_DENIED", object_type=view.__class__.__name__, metadata={"path": request.path, "method": request.method})
            return False
        if request.method not in SAFE_METHODS and staff.role == AdminStaff.Role.READ_ONLY:
            from .models import AdminAuditLog
            AdminAuditLog.objects.create(actor=request.user, actor_role=staff.role, action="ADMIN_PERMISSION_DENIED", object_type=view.__class__.__name__, metadata={"path": request.path, "method": request.method})
            return False
        return True

    def _is_mfa_required_for_role(self, staff):
        """Determine if MFA is required for a given staff role."""
        # High privilege roles always require MFA
        if staff.role in [AdminStaff.Role.SUPER_ADMIN, AdminStaff.Role.BILLING_ADMIN]:
            return True
        # Staff with MFA enforced requirement
        if staff.mfa_enforced:
            return True
        return False

    def _is_mfa_completed(self, staff):
        """Check if MFA is completed and verified."""
        # Staff must have MFA enabled and verified within last 24 hours
        if not staff.mfa_enabled or not staff.mfa_secret:
            return False
        # Check if MFA was verified recently (within 24 hours)
        if staff.mfa_last_verified_at:
            from django.utils import timezone
            time_diff = timezone.now() - staff.mfa_last_verified_at
            return time_diff.total_seconds() < 24 * 3600
        return False
