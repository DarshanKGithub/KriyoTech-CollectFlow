import hashlib
import secrets
from collections.abc import Mapping
from datetime import timedelta

from django.contrib.auth.models import update_last_login
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenObtainSerializer
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .mfa import credential_fingerprint, requires_mfa, verified_tokens
from .models import AdminAuditLog, AdminMFAChallenge, AdminStaff
from .totp import decrypt_secret, encrypt_secret, generate_totp_secret, get_totp_uri, verify_totp_token


class AdminTokenSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        try:
            # Authenticate without issuing usable tokens before the second factor.
            TokenObtainSerializer.validate(self, attrs)
        except AuthenticationFailed:
            AdminAuditLog.objects.create(action="ADMIN_LOGIN_FAILED", metadata={"email": str(attrs.get("email", ""))[:254]})
            raise
        staff = AdminStaff.objects.select_related("user").filter(user=self.user, is_active=True).first()
        if not staff:
            AdminAuditLog.objects.create(actor=self.user, action="ADMIN_LOGIN_DENIED", metadata={"reason": "not_internal_staff"})
            raise AuthenticationFailed("This account is not an active product administration staff account.")
        return login_for_staff(staff)


def login_for_staff(staff):
    if requires_mfa(staff):
        mode = "auth" if staff.mfa_enabled and staff.mfa_secret else "setup"
        raw = secrets.token_urlsafe(32)
        AdminMFAChallenge.objects.create(
            staff=staff, token_hash=hashlib.sha256(raw.encode()).hexdigest(), mode=mode,
            credential_fingerprint=credential_fingerprint(staff),
            setup_secret=encrypt_secret(generate_totp_secret()) if mode == "setup" else "",
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        return {"mfa_required": True, "mfa_setup_required": mode == "setup",
                "mfa_pending_token": raw, "role": staff.role}
    refresh = RefreshToken.for_user(staff.user)
    if api_settings.UPDATE_LAST_LOGIN:
        update_last_login(None, staff.user)
    AdminAuditLog.objects.create(actor=staff.user, actor_role=staff.role, action="ADMIN_LOGIN_SUCCEEDED")
    return {"access": str(refresh.access_token), "refresh": str(refresh), "role": staff.role, "mfa_required": False}


class AdminLoginView(TokenObtainPairView):
    serializer_class = AdminTokenSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "admin_login"


class AdminMFABase(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "admin_mfa"

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not isinstance(request.data, Mapping):
            raise ValidationError("Send an object with named fields.")

    def get_authenticate_header(self, request):
        return "MFA"

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        return response

    def challenge(self, request, mode):
        raw = request.data.get("mfa_pending_token")
        if not isinstance(raw, str) or not 1 <= len(raw) <= 256:
            raise ValidationError({"detail": "A valid mfa_pending_token is required."})
        challenge = AdminMFAChallenge.objects.select_for_update().filter(
            token_hash=hashlib.sha256(raw.encode()).hexdigest(), mode=mode,
            consumed_at__isnull=True, expires_at__gt=timezone.now(), attempts__lt=5,
        ).first()
        if not challenge:
            raise AuthenticationFailed("MFA challenge is invalid, expired or already used. Sign in again.")
        staff = AdminStaff.objects.select_for_update(of=("self",)).select_related("user").filter(
            pk=challenge.staff_id, is_active=True, user__is_active=True,
        ).first()
        if not staff or not constant_time_compare(challenge.credential_fingerprint, credential_fingerprint(staff)):
            raise AuthenticationFailed("Account credentials changed. Sign in again.")
        if (mode == "setup" and staff.mfa_enabled) or (mode == "auth" and not staff.mfa_enabled):
            raise AuthenticationFailed("MFA configuration changed. Sign in again.")
        return challenge, staff

    def complete(self, request, mode):
        challenge, staff = self.challenge(request, mode)
        secret = decrypt_secret(challenge.setup_secret if mode == "setup" else staff.mfa_secret)
        challenge.attempts += 1
        if not verify_totp_token(secret, request.data.get("code")):
            challenge.save(update_fields=["attempts"])
            AdminAuditLog.objects.create(actor=staff.user, actor_role=staff.role, action="ADMIN_MFA_VERIFICATION_FAILED")
            # Return inside the transaction so the failed-attempt counter commits.
            return Response({"detail": "Invalid two-factor authentication code."}, status=401)
        challenge.consumed_at = timezone.now()
        challenge.setup_secret = ""
        challenge.save(update_fields=["attempts", "consumed_at", "setup_secret"])
        staff.mfa_enabled = True
        staff.mfa_last_verified_at = timezone.now()
        staff.mfa_secret = encrypt_secret(secret)
        staff.save(update_fields=["mfa_enabled", "mfa_last_verified_at", "mfa_secret"])
        if api_settings.UPDATE_LAST_LOGIN:
            update_last_login(None, staff.user)
        AdminAuditLog.objects.create(actor=staff.user, actor_role=staff.role,
                                     action="ADMIN_MFA_ENABLED" if mode == "setup" else "ADMIN_LOGIN_SUCCEEDED_MFA")
        return Response(verified_tokens(staff))


class AdminMFAVerifyView(AdminMFABase):
    @transaction.atomic
    def post(self, request):
        return self.complete(request, "auth")


class AdminMFASetupView(AdminMFABase):
    @transaction.atomic
    def post(self, request):
        challenge, staff = self.challenge(request, "setup")
        secret = decrypt_secret(challenge.setup_secret)
        from partners.services import branding
        return Response({"secret": secret, "uri": get_totp_uri(secret, staff.user.email, issuer=f"{branding()['product_name']} Admin")},
                        headers={"Cache-Control": "no-store"})


class AdminMFAEnableView(AdminMFABase):
    @transaction.atomic
    def post(self, request):
        return self.complete(request, "setup")
