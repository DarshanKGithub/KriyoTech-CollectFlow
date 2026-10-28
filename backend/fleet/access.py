def fleet_enabled(tenant):
    if tenant.is_deleted:
        return False
    subscription=tenant.admin_subscriptions.order_by("-created_at").first()
    if subscription is None:
        return True
    if subscription.status in {"SUSPENDED","CHURNED","CANCELLED"}:
        return False
    from admin_console.services import entitlements_for
    return bool(entitlements_for(tenant).get("features",{}).get("fleet_management",{}).get("enabled"))
