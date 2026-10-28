from datetime import date
from calendar import monthrange
from django.db.models import F
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from admin_console.models import Subscription, TenantUsage
from .models import Invoice


@receiver(post_save, sender=Invoice, dispatch_uid="invoices.track_admin_usage")
def track_invoice_usage(sender, instance, created, **kwargs):
    if not created:
        return
    today = timezone.localdate()
    period_start = today.replace(day=1)
    last_day = monthrange(today.year, today.month)[1]
    period_end = today.replace(day=last_day)
    subscription = Subscription.objects.filter(tenant_id=instance.tenant_id).select_related("plan").order_by("-created_at").first()
    limit_value = subscription.plan.invoice_limit if subscription else None
    row, _ = TenantUsage.objects.get_or_create(tenant_id=instance.tenant_id, period_start=period_start, metric="invoices_uploaded",
        defaults={"period_end": period_end, "used_count": 0, "limit_value": limit_value})
    TenantUsage.objects.filter(pk=row.pk).update(used_count=F("used_count")+1, limit_value=limit_value, period_end=period_end)
