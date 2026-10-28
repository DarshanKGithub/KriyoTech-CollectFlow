from django.conf import settings
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView


class PasswordResetRequest(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    def post(self, request):
        email = str(request.data.get("email", "")).strip()
        user = get_user_model().objects.filter(email__iexact=email, is_active=True).first() if email else None
        if user:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            reset_url = f"{settings.FRONTEND_BASE_URL}/reset-password?uid={uid}&token={token}"
            try:
                send_mail(
                    "Reset your KriyoPay password",
                    f"A password reset was requested for your KriyoPay account.\n\nOpen this one-time link within 24 hours to choose a new password:\n{reset_url}\n\nIf you did not request this, you can ignore this email.",
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                    fail_silently=False,
                )
            except Exception:
                # Do not disclose whether an account exists or expose reset tokens in API errors.
                pass
        return Response({"detail": "If an active account exists for that email, password reset instructions have been sent."})


class PasswordResetConfirm(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    def post(self, request):
        uid, token, password = request.data.get("uid"), request.data.get("token"), request.data.get("new_password")
        if not all(isinstance(value, str) and value for value in (uid, token, password)):
            return Response({"error": "A valid reset link and new password are required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            user_id = force_str(urlsafe_base64_decode(uid))
            user = get_user_model().objects.get(pk=user_id, is_active=True)
        except (TypeError, ValueError, OverflowError, get_user_model().DoesNotExist):
            return Response({"error": "This reset link is invalid or has expired."}, status=status.HTTP_400_BAD_REQUEST)
        if not default_token_generator.check_token(user, token):
            return Response({"error": "This reset link is invalid or has expired."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            password_validation.validate_password(password, user)
        except ValidationError as error:
            return Response({"error": " ".join(error.messages)}, status=status.HTTP_400_BAD_REQUEST)
        user.set_password(password)
        user.save(update_fields=["password"])
        try:
            from admin_console.models import AdminAuditLog, AdminStaff
            staff = AdminStaff.objects.filter(user=user, is_active=True).first()
            if staff:
                AdminAuditLog.objects.create(actor=user, actor_role=staff.role, action="ADMIN_PASSWORD_RESET", object_type="User", object_id=str(user.pk))
        except Exception:
            pass
        return Response({"detail": "Password reset successful. You can now sign in with your new password."})
