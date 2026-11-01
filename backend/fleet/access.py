def fleet_enabled(tenant):
    from accounts.workspace_access import workspace_access_denial
    if workspace_access_denial(tenant, method="GET"):
        return False
    subscription=tenant.admin_subscriptions.order_by("-created_at").first()
    if subscription is None:
        return True
    from admin_console.services import entitlements_for
    return bool(entitlements_for(tenant).get("features",{}).get("fleet_management",{}).get("enabled"))
