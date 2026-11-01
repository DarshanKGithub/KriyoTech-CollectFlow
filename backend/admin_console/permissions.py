from rest_framework.permissions import BasePermission, SAFE_METHODS
from .models import AdminStaff
from .mfa import requires_mfa, verified_session


class IsAdminStaff(BasePermission):
    message = "KriyoPay internal staff access is required."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        staff = AdminStaff.objects.select_related("user").filter(user=request.user, is_active=True).first()
        if not staff:
            self.message = "This account is not assigned an active KriyoPay internal staff role."
            from .models import AdminAuditLog
            AdminAuditLog.objects.create(actor=request.user, action="ADMIN_ACCESS_DENIED", object_type=view.__class__.__name__, metadata={"path": request.path, "method": request.method})
            return False
        request.admin_staff = staff

        # Assurance belongs to this session, including optional staff MFA.
        if requires_mfa(staff):
            if not verified_session(staff, request.auth):
                self.message = "Staff access requires MFA for this session. Sign in again and complete two-factor authentication."
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
