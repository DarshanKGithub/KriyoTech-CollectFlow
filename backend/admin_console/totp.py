import base64
import hashlib
import hmac
import secrets
import struct
import time
import urllib.parse
from django.conf import settings
from django.core.signing import Signer, BadSignature
from cryptography.fernet import Fernet, InvalidToken


def _secret_cipher():
    key = hashlib.sha256(("kriyopay-admin-totp:" + settings.SECRET_KEY).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_secret(secret: str) -> str:
    """Encrypt at rest; legacy signed values are upgraded after verification."""
    return "fernet:" + _secret_cipher().encrypt(secret.encode()).decode()


def decrypt_secret(encrypted_secret: str) -> str:
    """Read encrypted secrets and the previous signed-only storage format."""
    if not encrypted_secret:
        return ""
    if encrypted_secret.startswith("fernet:"):
        try:
            return _secret_cipher().decrypt(encrypted_secret[7:].encode()).decode()
        except (InvalidToken, ValueError, UnicodeDecodeError):
            return ""
    signer = Signer(salt="admin_mfa_secret_encryption")
    try:
        return signer.unsign(encrypted_secret)
    except BadSignature:
        return ""


def generate_totp_secret() -> str:
    """Generate a random 160-bit Base32 secret (32 characters)."""
    random_bytes = secrets.token_bytes(20)
    return base64.b32encode(random_bytes).decode("utf-8").rstrip("=")


def get_totp_token(secret: str, interval: int = 30, for_time: float = None) -> str:
    """Calculate 6-digit TOTP code for given secret at specific timestamp (RFC 6238)."""
    if for_time is None:
        for_time = time.time()

    # Normalize base32 padding
    clean_secret = secret.upper().strip()
    missing_padding = len(clean_secret) % 8
    if missing_padding:
        clean_secret += "=" * (8 - missing_padding)

    try:
        key = base64.b32decode(clean_secret.encode("utf-8"), casefold=True)
    except Exception:
        return ""

    counter = int(for_time // interval)
    msg = struct.pack(">Q", counter)
    h = hmac.new(key, msg, hashlib.sha1).digest()
    offset = h[19] & 0x0F
    code = (struct.unpack(">I", h[offset : offset + 4])[0] & 0x7FFFFFFF) % 1000000
    return f"{code:06d}"


def verify_totp_token(secret: str, code: str, valid_window: int = 1) -> bool:
    """Validate 6-digit TOTP code against time drift window (+/- 1 interval by default)."""
    if not secret or not code:
        return False

    clean_code = str(code).strip()
    if len(clean_code) != 6 or not clean_code.isdigit():
        return False

    now = time.time()
    for i in range(-valid_window, valid_window + 1):
        expected_code = get_totp_token(secret, for_time=now + (i * 30))
        if expected_code and hmac.compare_digest(expected_code, clean_code):
            return True
    return False


def get_totp_uri(secret: str, email: str, issuer: str = "KriyoPay Admin") -> str:
    """Generate otpauth:// URI for authenticator QR codes."""
    label = urllib.parse.quote(f"{issuer}:{email}")
    issuer_param = urllib.parse.quote(issuer)
    return f"otpauth://totp/{label}?secret={secret}&issuer={issuer_param}&algorithm=SHA1&digits=6&period=30"
