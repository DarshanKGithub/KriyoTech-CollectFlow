from django.contrib.auth.models import update_last_login
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenObtainSerializer
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken
from admin_console.models import AdminStaff
from admin_console.auth import login_for_staff


class UnifiedLoginSerializer(TokenObtainPairSerializer):
    """Issue the ordinary JWT and tell the client which signed-in surface to open."""

    def validate(self, attrs):
        TokenObtainSerializer.validate(self, attrs)
        staff = AdminStaff.objects.filter(user=self.user, is_active=True).first()
        if staff:
            data = login_for_staff(staff)
        else:
            refresh = RefreshToken.for_user(self.user)
            data = {"access": str(refresh.access_token), "refresh": str(refresh)}
            if api_settings.UPDATE_LAST_LOGIN:
                update_last_login(None, self.user)
        data["account_type"] = "ADMIN" if staff else "WORKSPACE"
        if staff:
            data["admin_role"] = staff.role
        return data
