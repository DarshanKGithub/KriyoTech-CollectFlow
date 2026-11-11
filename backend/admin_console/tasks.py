from celery import shared_task
from django.db import transaction
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
import uuid
import logging
from kombu.exceptions import KombuError
from django.db.models import Q
from .billing import activate_paid_subscription, razorpay_request
from .invitation_delivery import reveal_token
from .models import InvitationDelivery, Payment, RazorpayWebhookEvent

logger = logging.getLogger(__name__)


@shared_task
def deliver_invitation(delivery_id):
    claim_token = uuid.uuid4()
    with transaction.atomic():
        delivery = InvitationDelivery.objects.select_for_update().select_related(
            "invitation__tenant"
        ).get(pk=delivery_id)
        now = timezone.now()
        if delivery.status in {
            InvitationDelivery.Status.SUBMITTED,
            InvitationDelivery.Status.CONSOLE_ONLY,
            InvitationDelivery.Status.CANCELLED,
        }:
            return delivery.status.lower()
        if delivery.next_attempt_at > now:
            return "retry scheduled"
        if (
            delivery.invitation.accepted_at
            or delivery.invitation.tenant.is_deleted
            or delivery.invitation.expires_at <= now
        ):
            delivery.status = InvitationDelivery.Status.CANCELLED
            delivery.encrypted_token = ""
            delivery.processing_token = None
            delivery.error_message = ""
            delivery.save(update_fields=["status", "encrypted_token", "processing_token", "error_message", "updated_at"])
            return "cancelled"
        if delivery.attempt_count >= 5:
            delivery.status = InvitationDelivery.Status.FAILED
            delivery.error_message = "Email delivery failed after five attempts. Resend the invitation to retry."
            delivery.save(update_fields=["status", "error_message", "updated_at"])
            return "attempts exhausted"
        delivery.attempt_count += 1
        delivery.status = InvitationDelivery.Status.PROCESSING
        delivery.processing_token = claim_token
        delay_seconds = min(60 * 2 ** (delivery.attempt_count - 1), 3600)
        delivery.next_attempt_at = now + timedelta(seconds=delay_seconds)
        delivery.error_message = ""
        delivery.save(update_fields=[
            "attempt_count", "status", "processing_token", "next_attempt_at", "error_message", "updated_at"
        ])
        invitation = delivery.invitation
        tenant_name = invitation.tenant.name
        recipient = invitation.email
        owner_name = invitation.tenant.memberships.filter(
            user__email__iexact=recipient
        ).values_list("user__first_name", flat=True).first() or recipient
        encrypted_token = delivery.encrypted_token

    try:
        token = reveal_token(encrypted_token)
        from partners.services import branding, frontend_link

        product_name = branding()["product_name"]
        accept_url = frontend_link("/invite/accept", {"token": token})
        sent = send_mail(
            f"Set up your {product_name} account for {tenant_name}",
            f"Hello {owner_name},\n\nYour workspace has been created. Set your password and activate access here (link expires in 7 days):\n{accept_url}\n",
            settings.DEFAULT_FROM_EMAIL,
            [recipient],
            fail_silently=False,
        )
        if sent != 1:
            raise RuntimeError("Email backend did not accept the invitation.")
    except Exception:
        with transaction.atomic():
            delivery = InvitationDelivery.objects.select_for_update().filter(pk=delivery_id).first()
            if delivery and delivery.status == InvitationDelivery.Status.PROCESSING and delivery.processing_token == claim_token:
                delivery.status = InvitationDelivery.Status.FAILED
                delivery.error_message = "Email delivery failed. The system will retry automatically; you can also resend it."
                delivery.processing_token = None
                delivery.save(update_fields=["status", "error_message", "processing_token", "updated_at"])
        logger.warning("Invitation delivery %s failed; retry will be scheduled.", delivery_id)
        return "failed"

    with transaction.atomic():
        delivery = InvitationDelivery.objects.select_for_update().get(pk=delivery_id)
        if delivery.status != InvitationDelivery.Status.PROCESSING or delivery.processing_token != claim_token:
            return "claim expired"
        delivery.status = (
            InvitationDelivery.Status.CONSOLE_ONLY
            if settings.EMAIL_BACKEND.endswith("console.EmailBackend")
            else InvitationDelivery.Status.SUBMITTED
        )
        delivery.encrypted_token = ""
        delivery.processing_token = None
        delivery.error_message = ""
        delivery.save(update_fields=[
            "status", "encrypted_token", "processing_token", "error_message", "updated_at"
        ])
    return delivery.status.lower()


@shared_task
def maintain_invitation_deliveries():
    now = timezone.now()
    due = InvitationDelivery.objects.filter(
        next_attempt_at__lte=now,
        attempt_count__lt=5,
    ).filter(
        Q(status__in=[InvitationDelivery.Status.PENDING, InvitationDelivery.Status.FAILED])
        | Q(status=InvitationDelivery.Status.PROCESSING)
    ).order_by("next_attempt_at").values_list("pk", flat=True)[:100]
    published = 0
    for delivery_id in due:
        try:
            deliver_invitation.delay(str(delivery_id))
            published += 1
        except KombuError:
            logger.warning("Invitation delivery %s remains queued because the task broker is unavailable.", delivery_id)
    return {"published": published}


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
