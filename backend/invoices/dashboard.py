"""Tenant-scoped dashboard aggregates; snapshots are distinct from upload history."""
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db.models import Case, CharField, Count, Sum, Value, When
from django.db.models.functions import TruncDate
from django.utils import timezone

from invoices.models import Invoice


def dashboard_analytics(tenant, days=30, include_finance=False):
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)
    start_at = timezone.make_aware(datetime.combine(start, time.min))
    end_at = timezone.make_aware(datetime.combine(today + timedelta(days=1), time.min))
    rows = Invoice.objects.filter(tenant=tenant)
    daily = rows.filter(created_at__gte=start_at, created_at__lt=end_at).order_by().annotate(
        day=TruncDate("created_at", tzinfo=timezone.get_current_timezone())
    ).values("day").annotate(count=Count("id"))
    counts = {row["day"]: row["count"] for row in daily}
    previous = rows.filter(created_at__gte=start_at - timedelta(days=days), created_at__lt=start_at).count()
    result = {
        "days": days,
        "start_date": start.isoformat(),
        "end_date": today.isoformat(),
        "as_of": timezone.now().isoformat(),
        "daily_uploads": [{"date": (start + timedelta(days=offset)).isoformat(), "count": counts.get(start + timedelta(days=offset), 0)} for offset in range(days)],
        "previous_uploads": previous,
    }
    if include_finance:
        from payments.services import with_invoice_balances
        eligible = with_invoice_balances(rows.filter(status__in=["APPROVED", "PAYMENT_READY", "EXPORTED"]).exclude(payment_status="CANCELLED"))
        eligible = eligible.filter(outstanding_balance__gt=0)
        buckets = eligible.order_by().annotate(bucket=Case(
            When(due_date__isnull=True, then=Value("NO_DUE_DATE")),
            When(due_date__gte=today, then=Value("NOT_OVERDUE")),
            When(due_date__gte=today - timedelta(days=7), then=Value("DAYS_1_7")),
            When(due_date__gte=today - timedelta(days=30), then=Value("DAYS_8_30")),
            default=Value("DAYS_31_PLUS"), output_field=CharField(),
        )).values("bucket").annotate(amount=Sum("outstanding_balance"), count=Count("id"))
        lookup = {row["bucket"]: row for row in buckets}
        result["payable_aging"] = [{"bucket": bucket, "amount": str(lookup.get(bucket, {}).get("amount", Decimal("0"))), "count": lookup.get(bucket, {}).get("count", 0)} for bucket in ["NOT_OVERDUE", "DAYS_1_7", "DAYS_8_30", "DAYS_31_PLUS", "NO_DUE_DATE"]]
    return result
