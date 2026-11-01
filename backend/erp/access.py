from django.utils import timezone
from accounts.models import Membership
from admin_console.services import has_feature
from accounts.workspace_access import workspace_access_denial
from .security import ERPError


def validate_background_access(connection, actor=None):
    tenant = connection.tenant
    actor = actor or connection.created_by
    membership = Membership.objects.filter(tenant=tenant, user=actor, is_active=True).first() if actor else None
    if workspace_access_denial(tenant, method="POST", membership=membership) or not connection.enabled:
        raise ERPError("Workspace or ERP connection is disabled.")
    subscription = tenant.admin_subscriptions.order_by("-created_at").first()
    if subscription:
        if subscription.status not in {"ACTIVE", "TRIAL", "GRACE_PERIOD"}:
            raise ERPError("ERP imports are paused until workspace billing is active.")
        if subscription.status == "TRIAL" and subscription.trial_ends_at and subscription.trial_ends_at <= timezone.now():
            raise ERPError("ERP imports are paused because the workspace trial expired.")
        if not has_feature(tenant, "api_access"):
            raise ERPError("The workspace plan no longer includes ERP/API access.")
    if not actor or not Membership.objects.filter(tenant=tenant, user=actor, is_active=True, branch_scope_enabled=False, role__in=["OWNER", "FINANCE"]).exists():
        raise ERPError("The integration owner no longer has workspace finance access.")
