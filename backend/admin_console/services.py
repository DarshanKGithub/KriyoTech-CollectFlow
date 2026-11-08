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
    from .models import Feature
    from .solution_catalog import FLEET_KEYS
    catalog = Feature.objects.filter(is_active=True)
    for feature in catalog:
        if feature.key not in values:
            inherited = feature.key in FLEET_KEYS and values.get("fleet_management", {}).get("enabled", False)
            if feature.key == "settlement_review":
                inherited = values.get("payment_tracking", {}).get("enabled", False)
            values[feature.key] = {"enabled": bool(inherited), "limit_value": None, "source": "legacy fleet" if inherited else "not included"}
        values[feature.key].update({"name": feature.name, "solution_name": feature.solution_name,
            "monthly_price": feature.monthly_price, "price_basis": feature.price_basis})
        if feature.key in FLEET_KEYS and not values.get("fleet_management", {}).get("enabled", False):
            values[feature.key]["enabled"] = False
    return {"plan": subscription.plan.name if subscription else None, "features": values}


def models_q_expiry(now):
    from django.db.models import Q
    return Q(expires_at__isnull=True) | Q(expires_at__gt=now)


def has_feature(tenant, key):
    from accounts.workspace_access import workspace_features_available
    if not workspace_features_available(tenant):
        return False
    return entitlements_for(tenant)["features"].get(key, {}).get("enabled", False)


def get_limit(tenant, metric):
    return entitlements_for(tenant)["features"].get(metric, {}).get("limit_value")
