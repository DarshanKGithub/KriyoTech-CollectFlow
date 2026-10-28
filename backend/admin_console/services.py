from django.utils import timezone
from .models import PlanFeature, TenantFeatureOverride


def entitlements_for(tenant):
    subscription = tenant.admin_subscriptions.select_related("plan").order_by("-created_at").first()
    values = {}
    if subscription:
        for row in PlanFeature.objects.filter(plan=subscription.plan, feature__is_active=True).select_related("feature"):
            values[row.feature.key] = {"enabled": row.enabled, "limit_value": row.limit_value, "limit_period": row.limit_period, "source": "plan"}
    now = timezone.now()
    # Apply historical overrides oldest first so the latest valid decision wins.
    for row in TenantFeatureOverride.objects.filter(tenant=tenant, feature__is_active=True).filter(models_q_expiry(now)).select_related("feature").order_by("created_at", "id"):
        values[row.feature.key] = {"enabled": row.enabled, "limit_value": row.limit_value, "limit_period": "", "source": "override", "expires_at": row.expires_at}
    return {"plan": subscription.plan.name if subscription else None, "features": values}


def models_q_expiry(now):
    from django.db.models import Q
    return Q(expires_at__isnull=True) | Q(expires_at__gt=now)


def has_feature(tenant, key):
    return entitlements_for(tenant)["features"].get(key, {}).get("enabled", False)


def get_limit(tenant, metric):
    return entitlements_for(tenant)["features"].get(metric, {}).get("limit_value")
