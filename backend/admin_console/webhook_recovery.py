from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from .models import RazorpayWebhookEvent

MAX_PUBLICATIONS = 20
MAX_PROCESSING_ATTEMPTS = 6


def publish_event(event_id):
    """Lease publication durably. A lost acknowledgement can safely duplicate a task."""
    with transaction.atomic():
        event = RazorpayWebhookEvent.objects.select_for_update().get(pk=event_id)
        now = timezone.now()
        if (event.status == "PROCESSED" or event.attempt_count >= MAX_PROCESSING_ATTEMPTS
                or event.publish_count >= MAX_PUBLICATIONS
                or event.next_attempt_at and event.next_attempt_at > now):
            return None
        event.publish_count += 1
        event.next_attempt_at = now + timedelta(minutes=5)
        event.save(update_fields=["publish_count", "next_attempt_at"])
        publication = event.publish_count
    try:
        from .tasks import process_razorpay_webhook
        process_razorpay_webhook.delay(str(event_id))
        return True
    except Exception:
        # Do not overwrite a worker's successful result after an uncertain publish.
        RazorpayWebhookEvent.objects.filter(pk=event_id, publish_count=publication).exclude(
            status__in=["PROCESSED", "PROCESSING"]
        ).update(status="FAILED", error_message="Broker publication failed; recovery scheduled.",
                 next_attempt_at=timezone.now() + timedelta(seconds=min(30 * 2 ** min(publication, 5), 900)))
        return False


def recover_events(limit=100):
    from django.db.models import Q
    ids = list(RazorpayWebhookEvent.objects.exclude(status="PROCESSED").filter(
        attempt_count__lt=MAX_PROCESSING_ATTEMPTS, publish_count__lt=MAX_PUBLICATIONS
    ).filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=timezone.now()))
               .order_by("received_at").values_list("pk", flat=True)[:limit])
    return sum(publish_event(event_id) is True for event_id in ids)
