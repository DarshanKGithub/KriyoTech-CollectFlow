from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied


USAGE_METRIC = "invoices_uploaded"


def current_invoice_limit(tenant, subscription=None):
    """Return the effective monthly invoice limit, preserving explicit zero overrides."""
    from admin_console.models import Subscription
    from admin_console.services import entitlements_for

    subscription = subscription or Subscription.objects.filter(
        tenant=tenant
    ).select_related("plan").order_by("-created_at").first()
    if subscription is None:
        return None
    entitlement = entitlements_for(tenant)["features"].get("invoice_upload")
    if entitlement and entitlement.get("limit_value") is not None:
        return entitlement["limit_value"]
    return subscription.plan.invoice_limit


def enforce_invoice_quota(tenant):
    """Serialize invoice creation per tenant and enforce its current monthly quota."""
    from admin_console.models import TenantUsage
    from tenants.models import Tenant

    with transaction.atomic():
        # This parent-row lock serializes all invoice creation paths, including intake workers.
        locked_tenant = Tenant.objects.select_for_update().get(pk=tenant.pk)
        limit = current_invoice_limit(locked_tenant)
        if limit is None:
            return
        today = timezone.localdate()
        start = today.replace(day=1)
        usage = TenantUsage.objects.select_for_update().filter(
            tenant=locked_tenant, period_start=start, metric=USAGE_METRIC
        ).first()
        used = usage.used_count if usage else 0
        if used >= limit:
            raise PermissionDenied(
                "Your monthly invoice limit has been reached. Contact your administrator to upgrade or request a temporary limit extension."
            )
