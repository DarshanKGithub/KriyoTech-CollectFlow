import hashlib
from datetime import timedelta

import pytest
from django.core.cache import cache
from django.core.signing import Signer
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import User
from .mfa import MFA_SESSION_SECONDS, verified_tokens
from .models import AdminMFAChallenge, AdminStaff
from .totp import decrypt_secret, encrypt_secret, generate_totp_secret, get_totp_token


@pytest.fixture
def staff(db):
    cache.clear()
    user = User.objects.create_user(username="mfa-test", email="mfa@example.test", password="secure-test-password-91")
    return AdminStaff.objects.create(user=user, role="SUPER_ADMIN")


def login(staff, path="/api/v1/auth/login"):
    response = APIClient().post(path, {"email": staff.user.email, "password": "secure-test-password-91"}, format="json")
    assert response.status_code == 200, response.data
    return response.data


def enroll(staff):
    data = login(staff)
    client = APIClient()
    body = {"mfa_pending_token": data["mfa_pending_token"]}
    setup = client.post("/api/v1/admin/auth/mfa/setup", body, format="json")
    assert setup.status_code == 200, setup.data
    body["code"] = get_totp_token(setup.data["secret"])
    response = client.post("/api/v1/admin/auth/mfa/enable", body, format="json")
    assert response.status_code == 200, response.data
    staff.refresh_from_db()
    return response.data, body


def admin_response(token):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client.get("/api/v1/admin/auth/me")


def test_enrollment_issues_no_tokens_until_code_and_challenge_cannot_be_reused(staff):
    data = login(staff)
    assert "access" not in data and "refresh" not in data
    row = AdminMFAChallenge.objects.get(token_hash=hashlib.sha256(data["mfa_pending_token"].encode()).hexdigest())
    assert row.setup_secret.startswith("fernet:")
    assert decrypt_secret(row.setup_secret) not in row.setup_secret
    tokens, body = enroll(staff)
    assert admin_response(tokens["access"]).status_code == 200
    assert APIClient().post("/api/v1/admin/auth/mfa/enable", body, format="json").status_code == 401
    # A parallel older setup cannot overwrite the now enrolled authenticator.
    assert APIClient().post("/api/v1/admin/auth/mfa/setup", {"mfa_pending_token": data["mfa_pending_token"]}, format="json").status_code == 401


@pytest.mark.parametrize("role", ["SUPER_ADMIN", "BILLING_ADMIN", "SUPPORT", "ADMIN"])
def test_password_only_session_denied_even_after_another_session_verified(staff, role):
    staff.role = role
    staff.mfa_enabled = True
    staff.mfa_secret = encrypt_secret(generate_totp_secret())
    staff.mfa_last_verified_at = timezone.now()
    staff.save()
    assert admin_response(str(AccessToken.for_user(staff.user))).status_code == 403
    assert admin_response(verified_tokens(staff)["access"]).status_code == 200
    assert "access" not in login(staff)


def test_refresh_preserves_assurance_but_does_not_extend_its_age(staff):
    tokens, _ = enroll(staff)
    response = APIClient().post("/api/v1/auth/refresh", {"refresh": tokens["refresh"]}, format="json")
    assert response.status_code == 200, response.data
    assert admin_response(response.data["access"]).status_code == 200
    original = AccessToken(tokens["access"])
    refreshed = AccessToken(response.data["access"])
    assert original["admin_mfa_at"] == refreshed["admin_mfa_at"]
    refreshed["admin_mfa_at"] = int(timezone.now().timestamp()) - MFA_SESSION_SECONDS - 1
    assert admin_response(str(refreshed)).status_code == 403


def test_challenges_expire_are_scoped_and_lock_after_five_failures(staff):
    tokens, _ = enroll(staff)
    pending = login(staff, "/api/v1/admin/auth/login")["mfa_pending_token"]
    client = APIClient()
    assert client.post("/api/v1/admin/auth/mfa/setup", {"mfa_pending_token": pending}, format="json").status_code == 401
    body = {"mfa_pending_token": pending, "code": "invalid"}
    for _ in range(5):
        assert client.post("/api/v1/admin/auth/mfa/verify", body, format="json").status_code == 401
    body["code"] = get_totp_token(decrypt_secret(staff.mfa_secret))
    assert client.post("/api/v1/admin/auth/mfa/verify", body, format="json").status_code == 401
    row = AdminMFAChallenge.objects.get(token_hash=hashlib.sha256(pending.encode()).hexdigest())
    assert row.attempts == 5
    fresh = login(staff)["mfa_pending_token"]
    AdminMFAChallenge.objects.filter(token_hash=hashlib.sha256(fresh.encode()).hexdigest()).update(expires_at=timezone.now()-timedelta(seconds=1))
    assert client.post("/api/v1/admin/auth/mfa/verify", {**body, "mfa_pending_token": fresh}, format="json").status_code == 401


def test_auth_challenge_is_consumed_once_and_both_login_routes_use_same_policy(staff):
    enroll(staff)
    pending = login(staff, "/api/v1/admin/auth/login")
    assert "access" not in pending
    body = {"mfa_pending_token": pending["mfa_pending_token"], "code": get_totp_token(decrypt_secret(staff.mfa_secret))}
    client = APIClient()
    response = client.post("/api/v1/admin/auth/mfa/verify", body, format="json")
    assert response.status_code == 200, response.data
    assert response.data["mfa_verified"] is True
    assert admin_response(response.data["access"]).status_code == 200
    assert client.post("/api/v1/admin/auth/mfa/verify", body, format="json").status_code == 401


@pytest.mark.parametrize("change", ["password", "disabled_user", "disabled_staff", "secret"])
def test_credentials_and_account_changes_invalidate_pending_or_completed_sessions(staff, change):
    tokens, _ = enroll(staff)
    pending = login(staff)["mfa_pending_token"]
    if change == "password":
        staff.user.set_password("new-secure-password-92")
        staff.user.save()
    elif change == "disabled_user":
        staff.user.is_active = False
        staff.user.save()
    elif change == "disabled_staff":
        staff.is_active = False
        staff.save()
    else:
        staff.mfa_secret = encrypt_secret(generate_totp_secret())
        staff.save()
    assert admin_response(tokens["access"]).status_code in {401, 403}
    response = APIClient().post("/api/v1/admin/auth/mfa/verify", {"mfa_pending_token": pending, "code": "123456"}, format="json")
    assert response.status_code == 401


def test_legacy_signed_secret_is_upgraded_only_after_successful_verification(staff):
    secret = generate_totp_secret()
    staff.mfa_enabled = True
    staff.mfa_secret = Signer(salt="admin_mfa_secret_encryption").sign(secret)
    staff.save()
    pending = login(staff)["mfa_pending_token"]
    response = APIClient().post("/api/v1/admin/auth/mfa/verify", {"mfa_pending_token": pending, "code": get_totp_token(secret)}, format="json")
    assert response.status_code == 200, response.data
    staff.refresh_from_db()
    assert staff.mfa_secret.startswith("fernet:")
    assert decrypt_secret(staff.mfa_secret) == secret


def test_password_jwt_alone_cannot_read_setup_secret_or_enable_mfa(staff):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(staff.user)}")
    assert client.post("/api/v1/admin/auth/mfa/setup", {}, format="json").status_code == 400
    assert client.post("/api/v1/admin/auth/mfa/enable", {"code": "123456"}, format="json").status_code == 400
