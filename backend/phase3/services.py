import hashlib
import hmac
import http.client
import ipaddress
import json
import socket
import uuid
from urllib.parse import urlsplit
from cryptography.fernet import Fernet
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from .models import WebhookEndpoint, WebhookDelivery

SUPPORTED_WEBHOOK_EVENTS = {"invoice.created", "invoice.submitted", "purchase_order.approved", "goods_receipt.recorded", "bank_transaction.reconciled", "webhook.test"}


def _fernet():
    key = getattr(settings, "WEBHOOK_FERNET_KEY", "")
    if not key: raise RuntimeError("Set WEBHOOK_FERNET_KEY before creating webhook subscriptions")
    try: return Fernet(key.encode())
    except (ValueError, TypeError): raise RuntimeError("WEBHOOK_FERNET_KEY is invalid; set a 32-byte URL-safe Base64 Fernet key") from None


def encrypt_signing_secret(secret):
    return _fernet().encrypt(secret.encode()).decode()


def decrypt_signing_secret(endpoint):
    return _fernet().decrypt(endpoint.encrypted_secret.encode()).decode()


def validate_public_webhook_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("Webhook URL must be an HTTPS URL on the standard port, without embedded credentials")
    try: addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)}
    except OSError: raise ValueError("Webhook hostname could not be resolved") from None
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError("Webhook hostname must resolve only to public IP addresses")
    return parsed, sorted(addresses)[0]


def queue_webhook_event(tenant, event_type, data):
    if event_type not in SUPPORTED_WEBHOOK_EVENTS: return 0
    event_id = uuid.uuid4()
    now = timezone.now()
    endpoints = [endpoint for endpoint in WebhookEndpoint.objects.filter(tenant=tenant, active=True) if event_type in endpoint.events]
    deliveries = [WebhookDelivery(endpoint=endpoint, tenant=tenant, event_id=event_id, event_type=event_type,
        payload={"id": str(event_id), "type": event_type, "created_at": now.isoformat(), "data": data}, status=WebhookDelivery.Status.QUEUED, next_attempt_at=now) for endpoint in endpoints]
    WebhookDelivery.objects.bulk_create(deliveries, ignore_conflicts=True)
    return len(deliveries)


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Connect to an already validated IP while preserving TLS SNI for the hostname."""
    def __init__(self, hostname, address, timeout=8):
        super().__init__(hostname, 443, timeout=timeout)
        self.address = address
    def connect(self):
        self.sock = socket.create_connection((self.address, self.port), self.timeout, self.source_address)
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)


def deliver_one(delivery):
    endpoint = delivery.endpoint
    try:
        parsed, address = validate_public_webhook_url(endpoint.url)
        secret = decrypt_signing_secret(endpoint)
        body = json.dumps(delivery.payload, separators=(",", ":")).encode("utf-8")
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        path = parsed.path or "/"
        if parsed.query: path += "?" + parsed.query
        connection = PinnedHTTPSConnection(parsed.hostname, address)
        try:
            connection.request("POST", path, body=body, headers={"Content-Type": "application/json", "X-KriyoPay-Event": delivery.event_type, "X-KriyoPay-Event-ID": str(delivery.event_id), "X-KriyoPay-Signature-256": "sha256=" + signature, "User-Agent": "KriyoPay-Webhooks/1.0"})
            response = connection.getresponse()
            code = response.status
            response.read(2048)
        finally:
            connection.close()
        delivery.response_code = code
        delivery.attempts += 1
        delivery.cycle_attempts += 1
        if 200 <= code < 300:
            delivery.status = WebhookDelivery.Status.DELIVERED; delivery.delivered_at = timezone.now(); delivery.error = ""; delivery.next_attempt_at = None
        else:
            delivery.error = f"Receiver returned HTTP {code}"
            schedule_retry(delivery)
    except Exception as exc:
        delivery.attempts += 1
        delivery.cycle_attempts += 1
        delivery.error = str(exc)[:500]
        schedule_retry(delivery)
    delivery.save()
    return delivery.status


def schedule_retry(delivery):
    if delivery.cycle_attempts >= 6:
        delivery.status = WebhookDelivery.Status.FAILED; delivery.next_attempt_at = None
    else:
        delivery.status = WebhookDelivery.Status.RETRY
        delivery.next_attempt_at = timezone.now() + timedelta(seconds=min(3600, 30 * (2 ** (delivery.cycle_attempts - 1))))


def deliver_due_webhooks(limit=100):
    now = timezone.now()
    from django.db.models import Q
    pending = WebhookDelivery.objects.select_related("endpoint").filter(status__in=[WebhookDelivery.Status.QUEUED, WebhookDelivery.Status.RETRY], endpoint__active=True).filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now))
    rows = list(pending.order_by("created_at")[:limit])
    for row in rows: deliver_one(row)
    return len(rows)
