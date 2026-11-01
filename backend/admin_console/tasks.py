from celery import shared_task
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
import uuid
from .billing import activate_paid_subscription, razorpay_request
from .models import Payment, RazorpayWebhookEvent


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 5})
def process_razorpay_webhook(self, event_id):
    try:
        claim_token = uuid.uuid4()
        with transaction.atomic():
            event = RazorpayWebhookEvent.objects.select_for_update().get(pk=event_id)
            if event.status == RazorpayWebhookEvent.Status.PROCESSED:
                return "already processed"
            now = timezone.now()
            if event.status == RazorpayWebhookEvent.Status.PROCESSING and event.next_attempt_at and event.next_attempt_at > now:
                return "already processing"
            if event.status == RazorpayWebhookEvent.Status.FAILED and event.next_attempt_at and event.next_attempt_at > now:
                return "retry scheduled"
            if event.attempt_count >= 6:
                return "attempts exhausted"
            event.status = RazorpayWebhookEvent.Status.PROCESSING
            event.attempt_count += 1
            event.error_message = ""
            event.next_attempt_at = now + timedelta(minutes=5)
            event.processing_token = claim_token
            event.save(update_fields=["status", "attempt_count", "error_message", "next_attempt_at", "processing_token"])
            payload = event.payload
            event_type = event.event_type

        # Provider reads happen after the claim transaction releases its row lock.
        entities = payload.get("payload") or {}
        payment_entity = (entities.get("payment") or {}).get("entity") or {}
        order_entity = (entities.get("order") or {}).get("entity") or {}
        refund_entity = (entities.get("refund") or {}).get("entity") or {}
        order_id = payment_entity.get("order_id") or order_entity.get("id")
        payment = Payment.objects.select_related("subscription", "requested_plan").filter(razorpay_order_id=order_id).first() if order_id else None
        server_order = None
        if event_type == "order.paid" and payment:
            server_order = razorpay_request("GET", f"/orders/{payment.razorpay_order_id}")

        with transaction.atomic():
            event = RazorpayWebhookEvent.objects.select_for_update().get(pk=event_id)
            if event.status == RazorpayWebhookEvent.Status.PROCESSED:
                return "already processed"
            if event.status != RazorpayWebhookEvent.Status.PROCESSING or event.processing_token != claim_token:
                return "claim expired"
            if order_id:
                payment = Payment.objects.select_for_update(of=("self",)).select_related("subscription", "requested_plan").filter(razorpay_order_id=order_id).first()
            if event_type == "payment.captured":
                if not payment or payment.amount != payment_entity.get("amount") or payment.currency != payment_entity.get("currency") or payment_entity.get("status") != "captured":
                    raise ValueError("Captured event does not match the stored order amount, currency, or status.")
                payment.razorpay_payment_id = payment_entity.get("id", "")
                activate_paid_subscription(payment, payload)
            elif event_type == "payment.failed":
                if payment:
                    # Late failures must never downgrade a captured or refunded payment.
                    Payment.objects.filter(pk=payment.pk, status__in=[Payment.Status.CREATED, Payment.Status.PENDING, Payment.Status.FAILED]).update(
                        status=Payment.Status.FAILED,
                        failure_reason=str(payment_entity.get("error_description") or payment_entity.get("error_reason") or "Payment failed")[:500],
                        raw_webhook_payload=payload)
            elif event_type == "order.paid":
                if payment:
                    if server_order.get("status") != "paid" or server_order.get("amount_paid", 0) < payment.amount or server_order.get("currency") != payment.currency:
                        raise ValueError("The fetched Razorpay order is not paid for the expected amount and currency.")
                    payment.raw_webhook_payload = payload
                    activate_paid_subscription(payment, payload)
            elif event_type in {"refund.processed", "refund.failed"}:
                from .refunds import observe
                observe(refund_entity, payload, forced_status="PROCESSED" if event_type == "refund.processed" else "FAILED")
            event.status = RazorpayWebhookEvent.Status.PROCESSED
            event.processed_at = timezone.now()
            event.next_attempt_at = None
            event.processing_token = None
            event.save(update_fields=["status", "processed_at", "next_attempt_at", "processing_token"])
        return "processed"
    except Exception:
        with transaction.atomic():
            event = RazorpayWebhookEvent.objects.select_for_update().filter(pk=event_id).first()
            if event and event.status != RazorpayWebhookEvent.Status.PROCESSED and event.processing_token == claim_token:
                delay = min(30 * (2 ** max(0, event.attempt_count - 1)), 900)
                event.status = RazorpayWebhookEvent.Status.FAILED
                event.error_message = "Event processing failed; inspect provider references before retrying."
                event.next_attempt_at = timezone.now() + timedelta(seconds=delay)
                event.processing_token = None
                event.save(update_fields=["status", "error_message", "next_attempt_at", "processing_token"])
        raise


@shared_task
def maintain_billing_webhooks():
    from .webhook_recovery import recover_events
    return {"published": recover_events()}
