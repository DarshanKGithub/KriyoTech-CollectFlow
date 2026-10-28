"""Server-side Google OAuth helpers for the read-only Gmail connector."""
import json
import urllib.error
import urllib.parse
import urllib.request
import base64
from pathlib import Path

from django.conf import settings


GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
OPENID_SCOPES = ("openid", "email", "profile")
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


def _read_oauth_client(file_setting, redirect_setting, label):
    configured = str(getattr(settings, file_setting, "") or "").strip()
    if not configured:
        raise RuntimeError(f"Set {file_setting} to the {label} OAuth client JSON file.")
    path = Path(configured)
    if not path.is_absolute():
        path = (settings.BASE_DIR / path).resolve()
    try:
        client_file = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise RuntimeError(f"{label} OAuth client file could not be read. Check {file_setting}.") from None
    details = client_file.get("web") or client_file.get("installed") or {}
    client_id = details.get("client_id", "")
    client_secret = details.get("client_secret", "")
    redirect_uri = str(getattr(settings, redirect_setting, "") or "").strip()
    if not client_id or not client_secret or not redirect_uri:
        raise RuntimeError(f"{label} OAuth client JSON needs a client ID, client secret, and redirect URI configuration.")
    allowed_redirects = details.get("redirect_uris", [])
    if redirect_uri not in allowed_redirects:
        raise RuntimeError(f"{redirect_setting} must exactly match a redirect URI registered in the {label} OAuth client.")
    return {"client_id": client_id, "client_secret": client_secret, "redirect_uri": redirect_uri}


def oauth_client():
    return _read_oauth_client("GOOGLE_GMAIL_CLIENT_FILE", "GOOGLE_GMAIL_REDIRECT_URI", "Gmail")


def signin_oauth_client():
    return _read_oauth_client("GOOGLE_SIGNIN_CLIENT_FILE", "GOOGLE_SIGNIN_REDIRECT_URI", "Google sign-in")


def authorization_url(state):
    client = oauth_client()
    params = {
        "client_id": client["client_id"],
        "redirect_uri": client["redirect_uri"],
        "response_type": "code",
        "scope": " ".join((*OPENID_SCOPES, GMAIL_READONLY_SCOPE)),
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)


def signin_authorization_url(state):
    client = signin_oauth_client()
    params = {"client_id": client["client_id"], "redirect_uri": client["redirect_uri"],
        "response_type": "code", "scope": " ".join(OPENID_SCOPES), "state": state}
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)


def _exchange_code(code, client, required_scope=None):
    body = urllib.parse.urlencode({
        "code": code,
        "client_id": client["client_id"],
        "client_secret": client["client_secret"],
        "redirect_uri": client["redirect_uri"],
        "grant_type": "authorization_code",
    }).encode("utf-8")
    request = urllib.request.Request(TOKEN_URL, data=body, method="POST", headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise RuntimeError("Google OAuth returned an unexpectedly large response.")
        token_data = json.loads(raw.decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, UnicodeDecodeError):
        raise RuntimeError("Google could not complete authorization. Restart the connection and check OAuth settings.") from None
    if not token_data.get("access_token"):
        raise RuntimeError("Google did not return an access token. Restart authorization.")
    if required_scope and required_scope not in str(token_data.get("scope", "")).split():
        raise RuntimeError("Gmail read-only access was not granted. Reconnect and approve the requested Gmail permission.")
    return token_data


def exchange_code(code):
    return _exchange_code(code, oauth_client(), GMAIL_READONLY_SCOPE)


def exchange_signin_code(code):
    return _exchange_code(code, signin_oauth_client())


def refresh_access_token(refresh_token):
    client = oauth_client()
    body = urllib.parse.urlencode({"client_id": client["client_id"], "client_secret": client["client_secret"],
        "refresh_token": refresh_token, "grant_type": "refresh_token"}).encode("utf-8")
    request = urllib.request.Request(TOKEN_URL, data=body, method="POST", headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.loads(response.read(1024 * 1024 + 1).decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try: detail = json.loads(exc.read(65536).decode("utf-8"))
        except (ValueError, UnicodeDecodeError): detail = {}
        if detail.get("error") == "invalid_grant": raise RuntimeError("GMAIL_REAUTH_REQUIRED") from None
        raise RuntimeError("Google could not refresh the Gmail connection.") from None
    except (urllib.error.URLError, json.JSONDecodeError, UnicodeDecodeError):
        raise RuntimeError("Google could not refresh the Gmail connection.") from None
    if not data.get("access_token"): raise RuntimeError("Google did not return a Gmail access token.")
    return data["access_token"]


def gmail_api(access_token, path, params=None):
    url = "https://gmail.googleapis.com/gmail/v1/users/me/" + path.lstrip("/")
    if params: url += "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {access_token}"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            # Base64 expands a 25 MiB attachment to roughly 33.4 MiB inside JSON.
            raw = response.read(36 * 1024 * 1024 + 1)
        if len(raw) > 36 * 1024 * 1024: raise RuntimeError("Gmail returned a response larger than the allowed limit.")
        return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 401: raise RuntimeError("GMAIL_REAUTH_REQUIRED") from None
        if exc.code == 403: raise RuntimeError("Gmail denied read-only mailbox access. Reconnect the mailbox.") from None
        raise RuntimeError("Gmail could not return mailbox data.") from None
    except (urllib.error.URLError, json.JSONDecodeError, UnicodeDecodeError):
        raise RuntimeError("Gmail could not return mailbox data.") from None


def decode_message_data(value):
    try: return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError): raise RuntimeError("Gmail returned an invalid attachment encoding.") from None


def google_profile(access_token):
    request = urllib.request.Request(USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read(256 * 1024 + 1)
        if len(raw) > 256 * 1024:
            raise RuntimeError("Google profile response exceeded the allowed size.")
        profile = json.loads(raw.decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, UnicodeDecodeError):
        raise RuntimeError("Could not verify the Google account for this Gmail connection.") from None
    email = str(profile.get("email", "")).strip().lower()
    if not profile.get("sub") or not email or profile.get("email_verified") is not True:
        raise RuntimeError("Google did not confirm a verified email address for this account.")
    return {"subject": str(profile["sub"]), "email": email}
