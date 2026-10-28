"""Durable refund intents. Only the initial claim may submit a provider POST."""
import uuid
from datetime import timedelta
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError
from .billing import GatewayError, GatewayUnavailable
from .models import AdminAuditLog, Payment, PaymentRefund, RefundIntent, Subscription


class RefundConflict(APIException):
    status_code = 409
    default_detail = "This refund conflicts with an existing request."


def reserve(payment_id, actor, amount, reason, key=None):
    reason = str(reason or "").strip()
    if not reason or len(reason) > 500:
        raise ValidationError({"reason": "Enter a refund reason of at most 500 characters."})
    if amount is not None and (isinstance(amount, bool) or not str(amount).isdigit() or int(amount) <= 0):
        raise ValidationError({"amount": "Enter a positive integer number of paise."})
    requested = int(amount) if amount is not None else None
    try:
        # Legacy callers get a deterministic key; new clients send a fresh key per intent.
        key = uuid.UUID(str(key)) if key else uuid.uuid5(uuid.NAMESPACE_URL, f"kriyopay-refund:{payment_id}:{requested}:{reason}")
    except (ValueError, TypeError, AttributeError):
        raise ValidationError({"idempotency_key": "Enter a valid UUID."}) from None
    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(pk=payment_id)
        existing = RefundIntent.objects.filter(payment=payment, request_key=key).first()
        if existing:
            if existing.reason != reason or existing.requested_amount != requested:
                raise RefundConflict("This request key belongs to a different amount or reason.")
            return existing
        if payment.status not in {"PAID", "PARTIALLY_REFUNDED"} or not payment.razorpay_payment_id:
            raise RefundConflict("Only captured Razorpay payments can be refunded.")
        recorded = payment.refunds.filter(status__in=["PENDING", "PROCESSED"]).aggregate(total=Sum("amount"))["total"] or 0
        reserved = payment.refund_intents.filter(refund__isnull=True).exclude(status="FAILED").aggregate(total=Sum("amount"))["total"] or 0
        available = payment.amount - recorded - reserved
        resolved = available if requested is None else requested
        if resolved <= 0 or resolved > available:
            raise RefundConflict("Refund amount exceeds the remaining unreserved refundable balance.")
        intent = RefundIntent.objects.create(payment=payment, request_key=key, requested_amount=requested,
            amount=resolved, reason=reason, created_by=actor)
        AdminAuditLog.objects.create(actor=actor, action="REFUND_INTENT_RESERVED", tenant=payment.tenant,
            object_type="RefundIntent", object_id=str(intent.pk), metadata={"amount_paise": resolved})
        return intent


@transaction.atomic
def observe(entity, payload=None, forced_status=None):
    """Shared provider-response/webhook state application; processed is terminal."""
    payment = Payment.objects.select_for_update().filter(razorpay_payment_id=entity.get("payment_id")).first()
    if not payment:
        return None
    amount = entity.get("amount")
    if not entity.get("id") or isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        raise ValueError("Refund is missing its ID or positive integer amount.")
    if entity.get("currency", payment.currency) != payment.currency:
        raise ValueError("Refund currency does not match payment.")
    notes = entity.get("notes") or {}
    intent_id = notes.get("kriyopay_refund_intent") if isinstance(notes, dict) else None
    intent = None
    if intent_id:
        try:
            intent = RefundIntent.objects.select_for_update().filter(payment=payment, pk=uuid.UUID(str(intent_id))).first()
        except (ValueError, TypeError):
            raise ValueError("Invalid refund intent reference.") from None
        if not intent or intent.amount != amount:
            raise ValueError("Refund does not match its reserved intent.")
    refund, created = PaymentRefund.objects.get_or_create(razorpay_refund_id=entity["id"], defaults={
        "tenant": payment.tenant, "payment": payment, "amount": amount,
        "reason": intent.reason if intent else "Observed in Razorpay", "created_by": intent.created_by if intent else None,
    })
    if refund.payment_id != payment.pk or refund.amount != amount:
        raise ValueError("Refund conflicts with stored payment or amount.")
    if not intent:
        intent = RefundIntent.objects.select_for_update().filter(payment=payment, refund=refund).first()
    if intent and intent.refund_id and intent.refund_id != refund.pk:
        raise ValueError("A second provider refund references the same intent.")
    status = forced_status or str(entity.get("status", "pending")).upper()
    if status not in {"PENDING", "PROCESSED", "FAILED"}:
        raise ValueError("Unsupported refund status.")
    # Late pending/failed events cannot downgrade a processed refund.
    if refund.status == "PROCESSED" or refund.status == "FAILED" and status == "PENDING":
        status = refund.status
    refund.status = status
    refund.raw_gateway_payload = payload or entity
    if status == "PROCESSED" and not refund.processed_at:
        refund.processed_at = timezone.now()
    refund.save()
    if intent:
        intent.refund = refund
        intent.status = status
        intent.save(update_fields=["refund", "status", "updated_at"])
    total = payment.refunds.filter(status="PROCESSED").aggregate(total=Sum("amount"))["total"] or 0
    if total:
        payment.status = "REFUNDED" if total >= payment.amount else "PARTIALLY_REFUNDED"
        payment.save(update_fields=["status"])
        if total >= payment.amount and payment.subscription_id:
            Subscription.objects.filter(pk=payment.subscription_id).update(status="PAST_DUE")
    if created or status == "PROCESSED":
        AdminAuditLog.objects.create(action="RAZORPAY_REFUND_" + status, tenant=payment.tenant,
            object_type="PaymentRefund", object_id=str(refund.pk), metadata={"refund_id": entity["id"]})
    return refund


def execute(intent, gateway):
    with transaction.atomic():
        current = RefundIntent.objects.select_for_update().select_related("payment").get(pk=intent.pk)
        if current.refund_id or current.status == "FAILED":
            return current
        submit = current.status == "RESERVED"
        if submit:
            current.status = "SUBMITTING"
            current.attempted_at = timezone.now()
            current.save(update_fields=["status", "attempted_at", "updated_at"])
        elif current.status == "SUBMITTING" and current.attempted_at > timezone.now() - timedelta(minutes=2):
            return current
    payment = current.payment
    try:
        if submit:
            entity = gateway("POST", f"/payments/{payment.razorpay_payment_id}/refund", {
                "amount": current.amount, "receipt": str(current.pk),
                "notes": {"reason": current.reason[:200], "kriyopay_refund_intent": str(current.pk)},
            })
            # Older mocks/provider responses may omit payment_id/notes; bind only
            # the direct response to the exact request we just made.
            entity = dict(entity)
            entity.setdefault("payment_id", payment.razorpay_payment_id)
            entity.setdefault("notes", {"kriyopay_refund_intent": str(current.pk)})
            if entity.get("payment_id") != payment.razorpay_payment_id or entity.get("amount") != current.amount:
                raise ValueError("Provider response does not match reserved refund.")
            notes = entity.get("notes") or {}
            if not isinstance(notes, dict) or notes.get("kriyopay_refund_intent", str(current.pk)) != str(current.pk):
                raise ValueError("Provider response has another intent reference.")
            entity["notes"] = {**notes, "kriyopay_refund_intent": str(current.pk)}
            observe(entity)
        else:
            # Read-only recovery. Absence from a bounded lookup is NOT proof that
            # a timed-out POST failed and never releases its reservation.
            for skip in range(0, 1000, 100):
                result = gateway("GET", f"/payments/{payment.razorpay_payment_id}/refunds?count=100&skip={skip}")
                items = result.get("items", [])
                if not isinstance(items, list):
                    raise ValueError("Invalid refund lookup.")
                matches = [row for row in items if isinstance(row, dict) and
                    (str(row.get("receipt", "")) == str(current.pk) or
                     isinstance(row.get("notes"), dict) and row["notes"].get("kriyopay_refund_intent") == str(current.pk))]
                if len(matches) > 1:
                    raise ValueError("Multiple provider refunds reference one intent.")
                if matches:
                    if matches[0].get("payment_id") != payment.razorpay_payment_id:
                        raise ValueError("Refund lookup returned another payment.")
                    recovered = dict(matches[0])
                    recovered["notes"] = {**(recovered.get("notes") or {}), "kriyopay_refund_intent": str(current.pk)}
                    observe(recovered)
                    break
                if len(items) < 100:
                    break
    except (GatewayError, GatewayUnavailable, ValueError, TypeError, KeyError, OSError):
        pass  # Ambiguous outcome is durable and never automatically resubmitted.
    RefundIntent.objects.filter(pk=current.pk, refund__isnull=True).exclude(status="FAILED").update(status="UNKNOWN")
    return RefundIntent.objects.select_related("refund").get(pk=current.pk)
