"""Verified-session fixtures for tests whose subject is staff business actions."""
from .mfa import verified_tokens
from .totp import encrypt_secret, generate_totp_secret


def authenticate_staff(client, staff):
    staff.mfa_enabled = True
    staff.mfa_secret = encrypt_secret(generate_totp_secret())
    staff.save(update_fields=["mfa_enabled", "mfa_secret"])
    client.force_authenticate(user=None, token=None)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {verified_tokens(staff)['access']}")
