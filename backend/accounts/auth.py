from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from admin_console.models import AdminStaff


class UnifiedLoginSerializer(TokenObtainPairSerializer):
    """Issue the ordinary JWT and tell the client which signed-in surface to open."""

    def validate(self, attrs):
        data = super().validate(attrs)
        staff = AdminStaff.objects.filter(user=self.user, is_active=True).first()
        data["account_type"] = "ADMIN" if staff else "WORKSPACE"
        if staff:
            data["admin_role"] = staff.role
        return data
