"""Shared workspace lifecycle rules for user, token, public-link and worker access."""
from django.utils import timezone


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
HARD_BLOCKED_SUBSCRIPTION_STATES = {"SUSPENDED", "CHURNED"}
READ_ONLY_SUBSCRIPTION_STATES = {"PAST_DUE", "CANCELLED", "ONBOARDING"}
OPERATIONAL_SUBSCRIPTION_STATES = {"ACTIVE", "TRIAL", "GRACE_PERIOD"}


def latest_subscription(tenant):
    return tenant.admin_subscriptions.order_by("-created_at").first()


def workspace_is_operational(tenant, subscription=None, now=None):
    """Whether scheduled or inbound work may create/update tenant records."""
    if not tenant or tenant.is_deleted:
        return False
    subscription = subscription if subscription is not None else latest_subscription(tenant)
    if subscription is None:
        return True
    if subscription.status not in OPERATIONAL_SUBSCRIPTION_STATES:
        return False
    now = now or timezone.now()
    return not (subscription.status == "TRIAL" and subscription.trial_ends_at and subscription.trial_ends_at <= now)


def workspace_features_available(tenant, subscription=None):
    """Feature entitlements survive read-only billing states, but not closure/suspension."""
    if not tenant or tenant.is_deleted:
        return False
    subscription = subscription if subscription is not None else latest_subscription(tenant)
    return not (subscription and subscription.status in HARD_BLOCKED_SUBSCRIPTION_STATES)


def workspace_access_denial(tenant, *, method="GET", membership=None, branch_aware=False,
        allow_billing_recovery=False, now=None):
    """Return a denial explanation or None using one lifecycle and branch policy."""
    if not tenant or tenant.is_deleted:
        return "This workspace is closed."
    if membership is not None and membership.tenant_id != tenant.id:
        return "Workspace membership is invalid."
    if membership is not None and not membership.is_active:
        return "Workspace membership is inactive."
    if membership is not None and membership.branch_scope_enabled and not branch_aware:
        return "Branch-scoped access is not supported for this entry point."
    subscription = latest_subscription(tenant)
    if not subscription:
        return None
    if subscription.status in HARD_BLOCKED_SUBSCRIPTION_STATES:
        return "This workspace is suspended. Contact workspace support."
    if subscription.status not in OPERATIONAL_SUBSCRIPTION_STATES | READ_ONLY_SUBSCRIPTION_STATES:
        return "This workspace subscription state does not permit access."
    read_only = subscription.status in READ_ONLY_SUBSCRIPTION_STATES
    now = now or timezone.now()
    if subscription.status == "TRIAL" and subscription.trial_ends_at and subscription.trial_ends_at <= now:
        read_only = True
    if read_only and method.upper() not in SAFE_METHODS and not allow_billing_recovery:
        return "This workspace is read-only. Review billing status or contact your administrator."
    return None
