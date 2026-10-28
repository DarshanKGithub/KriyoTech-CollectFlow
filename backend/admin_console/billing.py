import base64
import hashlib
import hmac
import json
import urllib.error
import urllib.request
from datetime import date, datetime, time
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from .models import AdminAuditLog, BillingInvoice, Payment, Subscription


class GatewayUnavailable(Exception):
    pass


class GatewayError(Exception):
    pass


def gateway_configured():
    # Checkout and server-side payment verification need API credentials.
    # Webhook verification uses its own secret and is configured separately.
    return bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET and settings.RAZORPAY_API_BASE_URL.startswith("https://"))


def razorpay_request(method, path, payload=None):
    if not (settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET):
        raise GatewayUnavailable("Razorpay API credentials are not configured.")
    root = settings.RAZORPAY_API_BASE_URL.rstrip("/")
    url = root + path
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    token = base64.b64encode(f"{settings.RAZORPAY_KEY_ID}:{settings.RAZORPAY_KEY_SECRET}".encode()).decode()
    request = urllib.request.Request(url, data=body, method=method, headers={"Authorization": f"Basic {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read(2048).decode("utf-8", errors="replace")
        raise GatewayError(f"Razorpay rejected the request (HTTP {error.code}): {detail}") from error
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise GatewayError("Razorpay could not be reached or returned an invalid response.") from error


def verify_checkout_signature(order_id, payment_id, signature):
    if not settings.RAZORPAY_KEY_SECRET:
        return False
    message = f"{order_id}|{payment_id}".encode("utf-8")
    expected = hmac.new(settings.RAZORPAY_KEY_SECRET.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, str(signature or ""))


def verify_webhook_signature(raw_body, signature):
    if not settings.RAZORPAY_WEBHOOK_SECRET:
        return False
    expected = hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, str(signature or ""))


def add_cycle(start, cycle):
    months = {Subscription.Cycle.MONTHLY: 1, Subscription.Cycle.QUARTERLY: 3, Subscription.Cycle.ANNUAL: 12}.get(cycle, 1)
    index = start.month - 1 + months
    year, month = start.year + index // 12, index % 12 + 1
    import calendar
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


@transaction.atomic
def activate_paid_subscription(payment, event_payload=None):
    incoming = payment
    payment = Payment.objects.select_for_update().get(pk=incoming.pk)
    if payment.status in {Payment.Status.PAID, Payment.Status.PARTIALLY_REFUNDED, Payment.Status.REFUNDED}:
        return
    payment.razorpay_payment_id = incoming.razorpay_payment_id or payment.razorpay_payment_id
    payment.razorpay_signature = incoming.razorpay_signature or payment.razorpay_signature
    today = timezone.localdate()
    invoice_number = f"KP-{today:%Y%m%d}-{str(payment.id).replace('-', '')[:8].upper()}"
    payment.status = Payment.Status.PAID
    payment.paid_at = timezone.now()
    payment.raw_webhook_payload = event_payload or payment.raw_webhook_payload
    payment.save(update_fields=["status", "paid_at", "raw_webhook_payload", "razorpay_payment_id", "razorpay_signature"])
    if not payment.subscription_id:
        return
    subscription = Subscription.objects.select_for_update().get(pk=payment.subscription_id)
    # Refresh the caller's cached relation for existing checkout responses.
    incoming.subscription = subscription
    period_date = timezone.localdate(subscription.current_period_end) if subscription.current_period_end else None
    start = period_date if subscription.status == Subscription.Status.ACTIVE and period_date and period_date >= today else today
    period_end = add_cycle(start, payment.billing_cycle)
    subscription.plan = payment.requested_plan or subscription.plan
    subscription.billing_cycle = payment.billing_cycle
    subscription.status = Subscription.Status.ACTIVE
    subscription.current_period_end = timezone.make_aware(datetime.combine(period_end, time.min))
    subscription.next_billing_at = timezone.make_aware(datetime.combine(period_end, time.min))
    subscription.trial_ends_at = None
    subscription.grace_ends_at = None
    subscription.save(update_fields=["plan", "billing_cycle", "status", "current_period_end", "next_billing_at", "trial_ends_at", "grace_ends_at", "updated_at"])
    BillingInvoice.objects.get_or_create(invoice_number=invoice_number, defaults={
        "tenant": payment.tenant, "subscription": subscription, "plan_name": subscription.plan.name,
        "billing_period_start": start, "billing_period_end": period_end,
        "base_amount": payment.amount, "total_amount": payment.amount, "currency": payment.currency,
        "status": BillingInvoice.Status.PAID, "paid_at": payment.paid_at,
    })
    AdminAuditLog.objects.create(action="SUBSCRIPTION_PAYMENT_CONFIRMED", tenant=payment.tenant,
        object_type="Payment", object_id=str(payment.id), metadata={"amount_paise": payment.amount, "cycle": payment.billing_cycle, "plan": subscription.plan.slug})
