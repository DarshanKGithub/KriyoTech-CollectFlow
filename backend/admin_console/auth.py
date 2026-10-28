from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from django.utils import timezone
from .models import AdminAuditLog, AdminStaff
from .totp import decrypt_secret, encrypt_secret, generate_totp_secret, get_totp_uri, verify_totp_token


signer = TimestampSigner(salt="admin_mfa_pending")


class AdminTokenSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        try:
            data = super().validate(attrs)
        except AuthenticationFailed:
            AdminAuditLog.objects.create(action="ADMIN_LOGIN_FAILED", metadata={"email": str(attrs.get("email", ""))[:254]})
            raise

        staff = AdminStaff.objects.filter(user=self.user, is_active=True).first()
        if not staff:
            AdminAuditLog.objects.create(actor=self.user, action="ADMIN_LOGIN_DENIED", metadata={"reason": "not_internal_staff"})
            raise AuthenticationFailed("This account is not an active KriyoPay internal staff account.")

        is_high_privilege = staff.role in [AdminStaff.Role.SUPER_ADMIN, AdminStaff.Role.BILLING_ADMIN]
        mfa_required = staff.mfa_enabled or staff.mfa_enforced or is_high_privilege

        if mfa_required:
            if not staff.mfa_enabled or not staff.mfa_secret:
                # High privilege role without MFA set up must onboard MFA
                staff.mfa_secret = encrypt_secret(generate_totp_secret())
                staff.save(update_fields=["mfa_secret"])
                pending_token = signer.sign(f"{self.user.id}:{staff.id}:setup")
                return {
                    "mfa_required": True,
                    "mfa_setup_required": True,
                    "mfa_pending_token": pending_token,
                    "role": staff.role,
                    "detail": "Two-factor authentication setup is required for your staff role."
                }

            pending_token = signer.sign(f"{self.user.id}:{staff.id}:auth")
            return {
                "mfa_required": True,
                "mfa_pending_token": pending_token,
                "role": staff.role,
                "detail": "Two-factor authentication code required."
            }

        AdminAuditLog.objects.create(actor=self.user, actor_role=staff.role, action="ADMIN_LOGIN_SUCCEEDED")
        data["role"] = staff.role
        data["mfa_required"] = False
        return data


class AdminLoginView(TokenObtainPairView):
    serializer_class = AdminTokenSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "admin_login"


class AdminMFAVerifyView(APIView):
    # MFA verification is the second login step, so no JWT exists yet. The
    # signed, short-lived pending token in the request body is the credential.
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "admin_login"

    def post(self, request):
        pending_token = request.data.get("mfa_pending_token")
        code = request.data.get("code")

        if not pending_token or not code:
            raise ValidationError({"detail": "mfa_pending_token and code are required."})

        try:
            # Valid for 300 seconds (5 minutes)
            unsigned_data = signer.unsign(pending_token, max_age=300)
            user_id, staff_id, mode = unsigned_data.split(":")
        except SignatureExpired:
            raise AuthenticationFailed("2FA verification session expired. Please sign in again.")
        except (BadSignature, ValueError):
            raise AuthenticationFailed("Invalid 2FA verification token.")

        staff = AdminStaff.objects.filter(id=staff_id, user_id=user_id, is_active=True).first()
        if not staff:
            raise AuthenticationFailed("Account or staff assignment invalid.")
        if mode != "auth" or not staff.mfa_enabled or not staff.mfa_secret:
            raise AuthenticationFailed("Two-factor authentication is not enabled for this account. Sign in again to finish setup.")

        raw_secret = decrypt_secret(staff.mfa_secret) if staff.mfa_secret else ""
        if not verify_totp_token(raw_secret, code):
            AdminAuditLog.objects.create(
                actor=staff.user,
                actor_role=staff.role,
                action="ADMIN_MFA_VERIFICATION_FAILED"
            )
            raise AuthenticationFailed("Invalid two-factor authentication code.")

        staff.mfa_last_verified_at = timezone.now()
        staff.save(update_fields=["mfa_last_verified_at"])

        refresh = RefreshToken.for_user(staff.user)
        AdminAuditLog.objects.create(
            actor=staff.user,
            actor_role=staff.role,
            action="ADMIN_LOGIN_SUCCEEDED_MFA"
        )
        return Response({"access": str(refresh.access_token), "refresh": str(refresh), "role": staff.role, "mfa_required": False})


class AdminMFASetupView(APIView):
    def post(self, request):
        staff = AdminStaff.objects.filter(user=request.user, is_active=True).first()
        if not staff:
            raise AuthenticationFailed("Staff profile required.")

        if staff.mfa_enabled:
            return Response({"detail": "2FA already enabled."}, status=status.HTTP_400_BAD_REQUEST)

        secret = decrypt_secret(staff.mfa_secret) if staff.mfa_secret else generate_totp_secret()
        if not staff.mfa_secret:
            staff.mfa_secret = encrypt_secret(secret)
            staff.save(update_fields=["mfa_secret"])

        return Response({
            "secret": secret,
            "uri": get_totp_uri(secret, request.user.email)
        })


class AdminMFAEnableView(APIView):
    def post(self, request):
        code = request.data.get("code")
        staff = AdminStaff.objects.filter(user=request.user, is_active=True).first()

        if not staff or not staff.mfa_secret:
            raise ValidationError({"detail": "2FA setup not initiated."})

        raw_secret = decrypt_secret(staff.mfa_secret)
        if not verify_totp_token(raw_secret, code):
            raise ValidationError({"detail": "Invalid verification code."})

        staff.mfa_enabled = True
        staff.mfa_last_verified_at = timezone.now()
        staff.save(update_fields=["mfa_enabled", "mfa_last_verified_at"])

        AdminAuditLog.objects.create(
            actor=staff.user, actor_role=staff.role, action="ADMIN_MFA_ENABLED"
        )
        return Response({"detail": "2FA enabled successfully."})

