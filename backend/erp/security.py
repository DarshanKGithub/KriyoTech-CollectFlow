import http.client
import ipaddress
import json
import socket
from urllib.parse import urlsplit
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


class ERPError(Exception):
    """A sanitized, user-visible connector error."""


def cipher():
    key = settings.ERP_CREDENTIALS_KEY or settings.WEBHOOK_FERNET_KEY
    if not key:
        raise ERPError("Configure ERP_CREDENTIALS_KEY before saving ERP credentials.")
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError):
        raise ERPError("ERP credential encryption key is invalid.") from None


def encrypt(credentials):
    return cipher().encrypt(json.dumps(credentials).encode()).decode()


def credentials(connection):
    if not connection.encrypted_credentials:
        return {}
    try:
        return json.loads(cipher().decrypt(connection.encrypted_credentials.encode()))
    except (InvalidToken, ValueError):
        raise ERPError("Saved credentials could not be decrypted. Restore the encryption key or reconnect.") from None


def validate_origin(url):
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        raise ERPError("Enter a valid ERP URL.") from None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ERPError("ERP URL must use HTTP(S), without embedded credentials or fragments.")
    origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    trusted = origin in settings.ERP_TRUSTED_ORIGINS
    if not trusted and (parsed.scheme != "https" or port not in {None, 443}):
        raise ERPError("Use public HTTPS on port 443, or ask the operator to approve this exact ERP origin.")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)}
    except OSError:
        raise ERPError("ERP hostname could not be resolved.") from None
    if not addresses or (not trusted and any(not ipaddress.ip_address(address).is_global for address in addresses)):
        raise ERPError("Private ERP origins must be explicitly approved by the server operator.")
    return parsed, sorted(addresses)[0]


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, port, address):
        super().__init__(host, port, timeout=20)
        self.address = address

    def connect(self):
        self.sock = socket.create_connection((self.address, self.port), self.timeout)
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)


class PinnedHTTP(http.client.HTTPConnection):
    def __init__(self, host, port, address):
        super().__init__(host, port, timeout=20)
        self.address = address

    def connect(self):
        self.sock = socket.create_connection((self.address, self.port), self.timeout)


def request(url, method="GET", headers=None, body=None, xml=False):
    parsed, address = validate_origin(url)
    transport = PinnedHTTPS if parsed.scheme == "https" else PinnedHTTP
    conn = transport(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), address)
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    try:
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        data = response.read(5 * 1024 * 1024 + 1)
        if len(data) > 5 * 1024 * 1024:
            raise ERPError("ERP response exceeds 5 MB. Reduce the page size.")
        if not 200 <= response.status < 300:
            # Never persist provider bodies; they can include credentials or PII.
            raise ERPError(f"ERP returned HTTP {response.status}. Check credentials, permissions and entity configuration.")
        if xml:
            return data
        result = json.loads(data or b"{}")
        if not isinstance(result, dict):
            raise ERPError("ERP returned an unexpected response.")
        return result
    except (OSError, http.client.HTTPException, ValueError):
        raise ERPError("ERP connection failed or returned an invalid response. Check the connection and sync history.") from None
    finally:
        conn.close()
