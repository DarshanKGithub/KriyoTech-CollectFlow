from celery import shared_task
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from .billing import activate_paid_subscription, razorpay_request
from .models import Payment, RazorpayWebhookEvent


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 5})
def process_razorpay_webhook(self, event_id):
    try:
        with transaction.atomic():
            event = RazorpayWebhookEvent.objects.select_for_update().get(pk=event_id)
            if event.status == RazorpayWebhookEvent.Status.PROCESSED:
                return "already processed"
            if event.attempt_count >= 6:
                return "attempts exhausted"
            event.status = RazorpayWebhookEvent.Status.PROCESSING
            event.attempt_count += 1
            event.error_message = ""
            event.save(update_fields=["status", "attempt_count", "error_message"])
            payload = event.payload
            entities = payload.get("payload") or {}
            payment_entity = (entities.get("payment") or {}).get("entity") or {}
            order_entity = (entities.get("order") or {}).get("entity") or {}
            refund_entity = (entities.get("refund") or {}).get("entity") or {}
            order_id = payment_entity.get("order_id") or order_entity.get("id")
            payment = Payment.objects.select_related("subscription", "requested_plan").filter(razorpay_order_id=order_id).first() if order_id else None

            if event.event_type == "payment.captured":
                if not payment or payment.amount != payment_entity.get("amount") or payment.currency != payment_entity.get("currency") or payment_entity.get("status") != "captured":
                    raise ValueError("Captured event does not match the stored order amount, currency, or status.")
                payment.razorpay_payment_id = payment_entity.get("id", "")
                activate_paid_subscription(payment, payload)
            elif event.event_type == "payment.failed":
                if payment:
                    # Failed attempts can arrive after a successful retry on the
                    # same order. Never downgrade a captured or refunded payment.
                    Payment.objects.filter(pk=payment.pk, status__in=[Payment.Status.CREATED, Payment.Status.PENDING, Payment.Status.FAILED]).update(
                        status=Payment.Status.FAILED,
                        failure_reason=str(payment_entity.get("error_description") or payment_entity.get("error_reason") or "Payment failed")[:500],
                        raw_webhook_payload=payload)
            elif event.event_type == "order.paid":
                if payment:
                    server_order = razorpay_request("GET", f"/orders/{payment.razorpay_order_id}")
                    if server_order.get("status") != "paid" or server_order.get("amount_paid", 0) < payment.amount or server_order.get("currency") != payment.currency:
                        raise ValueError("The fetched Razorpay order is not paid for the expected amount and currency.")
                    payment.raw_webhook_payload = payload
                    activate_paid_subscription(payment, payload)
            elif event.event_type in {"refund.processed", "refund.failed"}:
                from .refunds import observe
                observe(refund_entity, payload, forced_status="PROCESSED" if event.event_type == "refund.processed" else "FAILED")

            event.status = RazorpayWebhookEvent.Status.PROCESSED
            event.processed_at = timezone.now()
            event.save(update_fields=["status", "processed_at"])
        return "processed"
    except Exception:
        RazorpayWebhookEvent.objects.filter(pk=event_id).exclude(status=RazorpayWebhookEvent.Status.PROCESSED).update(
            status=RazorpayWebhookEvent.Status.FAILED,
            attempt_count=F("attempt_count") + 1,
            error_message="Event processing failed; inspect provider references before retrying.",
        )
        raise


@shared_task
def maintain_billing_webhooks():
    from .webhook_recovery import recover_events
    return {"published": recover_events()}
