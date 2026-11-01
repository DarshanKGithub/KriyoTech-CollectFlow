from datetime import date
from calendar import monthrange
from django.db.models import F
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from admin_console.models import TenantUsage
from .quota import current_invoice_limit, USAGE_METRIC
from .models import Invoice


@receiver(post_save, sender=Invoice, dispatch_uid="invoices.track_admin_usage")
def track_invoice_usage(sender, instance, created, **kwargs):
    if not created:
        return
    today = timezone.localdate()
    period_start = today.replace(day=1)
    last_day = monthrange(today.year, today.month)[1]
    period_end = today.replace(day=last_day)
    limit_value = current_invoice_limit(instance.tenant)
    row, _ = TenantUsage.objects.get_or_create(tenant_id=instance.tenant_id, period_start=period_start, metric=USAGE_METRIC,
        defaults={"period_end": period_end, "used_count": 0, "limit_value": limit_value})
    TenantUsage.objects.filter(pk=row.pk).update(used_count=F("used_count")+1, limit_value=limit_value, period_end=period_end)
