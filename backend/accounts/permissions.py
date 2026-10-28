from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission, SAFE_METHODS
from .models import Membership

class HasTenantMembership(BasePermission):
    def has_permission(self, request, view):
        # DRF can call this permission for anonymous requests before an
        # authentication class raises its own response. Never query the UUID
        # user field with AnonymousUser.
        if not request.user or not request.user.is_authenticated:
            return False

        memberships = Membership.objects.filter(user=request.user, is_active=True)
        workspace = request.headers.get("X-Workspace")
        if workspace: memberships = memberships.filter(tenant__workspace_key=workspace)
        membership = memberships.select_related("tenant").first()
        if not membership: return False
        request.tenant, request.membership = membership.tenant, membership
        if membership.role == Membership.Role.DRIVER:
            path = request.path_info
            driver_allowed = path.startswith("/api/v1/fleet/") or path in {
                "/api/v1/auth/me", "/api/v1/auth/workspaces", "/api/v1/auth/logout",
            }
            if not driver_allowed:
                raise PermissionDenied("Driver accounts can only access their fleet workspace.")
        role = membership.role
        path = request.path_info
        method = request.method.upper()
        if membership.branch_scope_enabled and not (
            (path == "/api/v1/auth/me" and method == "GET")
            or (path == "/api/v1/branches" and method == "GET")
            or (path == "/api/v1/auth/logout" and method == "POST")
        ):
            raise PermissionDenied("Branch access is not enabled for this workflow yet. Ask an owner to disable branch scope or use an unscoped workspace role.")
        owner = {Membership.Role.OWNER}
        finance = owner | {Membership.Role.FINANCE}
        approvers = finance | {Membership.Role.APPROVER}
        invoice_readers = approvers | {Membership.Role.PURCHASE, Membership.Role.AUDITOR, Membership.Role.STORE}
        if role == Membership.Role.AUDITOR and method not in SAFE_METHODS:
            raise PermissionDenied("Auditor access is read-only.")
        # Protect the highest impact records at the API boundary in addition to
        # view-level checks. This keeps newly added actions from inheriting broad access.
        if path == "/api/v1/branches" and membership.branch_scope_enabled and method == "GET":
            allowed = {role}
        elif path.startswith("/api/v1/users") or path.startswith("/api/v1/branches") or path.startswith("/api/v1/branch-assignments"):
            allowed = owner
        elif path.startswith("/api/v1/invoices"):
            path_action = path.rstrip("/").rsplit("/", 1)[-1]
            allowed = invoice_readers if method in SAFE_METHODS else finance
            if method == "POST" and path_action in {"approve", "reject"}:
                allowed = approvers
            elif method == "POST" and path_action == "confirm-extraction":
                allowed = finance | {Membership.Role.PURCHASE}
            elif method == "POST" and path_action == "submit-for-approval":
                allowed = finance
        elif path.startswith("/api/v1/payments") or path.startswith("/api/v1/bank-reconciliation") or path.startswith("/api/v1/settlements/"):
            allowed = finance | ({Membership.Role.AUDITOR} if method in SAFE_METHODS and "suggestions_for" not in request.query_params else set())
            if path.rstrip("/") == "/api/v1/payments/instructions" and method in SAFE_METHODS:
                allowed = approvers | {Membership.Role.AUDITOR}
            elif path.startswith("/api/v1/payments/instructions/") and path.rstrip("/").endswith("/decision"):
                allowed = approvers
        elif path.startswith("/api/v1/exports/") or path.startswith("/api/v1/reports/") or path.startswith("/api/v1/audit-logs"):
            allowed = finance | {Membership.Role.AUDITOR} if method in SAFE_METHODS else finance
        elif path.startswith("/api/v1/purchase-orders"):
            allowed = (finance | {Membership.Role.PURCHASE, Membership.Role.AUDITOR}) if method in SAFE_METHODS else finance | {Membership.Role.PURCHASE}
        elif path.startswith("/api/v1/grns"):
            allowed = (finance | {Membership.Role.PURCHASE, Membership.Role.STORE, Membership.Role.AUDITOR}) if method in SAFE_METHODS else finance | {Membership.Role.PURCHASE, Membership.Role.STORE}
        elif path.startswith("/api/v1/fleet/"):
            fleet_roles = finance | {Membership.Role.FLEET, Membership.Role.DRIVER}
            fleet_staff = finance | {Membership.Role.FLEET}
            path_tail = path.removeprefix("/api/v1/fleet/").strip("/")
            if path_tail == "my-trips":
                allowed = {Membership.Role.DRIVER}
            elif path_tail == "driver-ledger.csv" or path_tail == "driver-earnings":
                allowed = finance | {Membership.Role.FLEET} | ({Membership.Role.AUDITOR} if method in SAFE_METHODS else set())
            elif path_tail.startswith("trips/") and path_tail.rsplit("/", 1)[-1] in {"approve", "reject"}:
                allowed = approvers
            elif path_tail.startswith("driver-salary-adjustments/") and path_tail.rsplit("/", 1)[-1] in {"approve", "reject"}:
                allowed = approvers
            elif path_tail == "exceptions" or path_tail.startswith("exceptions/") or path_tail.startswith("detention/"):
                allowed = finance | {Membership.Role.FLEET, Membership.Role.APPROVER}
            elif path_tail.startswith("return-loads/") and path_tail.rsplit("/",1)[-1] in {"confirm","decline"}:
                allowed = finance | {Membership.Role.FLEET,Membership.Role.PURCHASE,Membership.Role.APPROVER}
            elif path_tail == "route-integration" or (path_tail.startswith("trips/") and path_tail.endswith("/refresh-route")):
                allowed = finance | {Membership.Role.FLEET,Membership.Role.APPROVER}
            elif path_tail == "driver-salaries" or path_tail.startswith("driver-salaries/"):
                if path_tail.endswith("/payments"):
                    allowed = finance
                elif "/adjustments/" in path_tail and path_tail.rsplit("/", 1)[-1] in {"approve", "reject"}:
                    allowed = approvers
                elif path_tail.endswith("/approve") or path_tail.endswith("/reject"):
                    allowed = approvers
                elif method in SAFE_METHODS:
                    allowed = finance | {Membership.Role.FLEET} | ({Membership.Role.AUDITOR} if method in SAFE_METHODS else set())
                else:
                    allowed = fleet_staff
            elif path_tail == "driver-advances" or path_tail.startswith("driver-advances/") or path_tail == "driver-pay-policies" or path_tail.startswith("driver-pay-policies/"):
                allowed = finance | {Membership.Role.FLEET} | ({Membership.Role.AUDITOR} if method in SAFE_METHODS else set())
            else:
                allowed = fleet_roles | {Membership.Role.PURCHASE, Membership.Role.STORE, Membership.Role.APPROVER, Membership.Role.AUDITOR}
                if method not in SAFE_METHODS:
                    allowed = fleet_roles | {Membership.Role.PURCHASE}
        else:
            allowed = None
        if allowed is not None and role not in allowed:
            raise PermissionDenied("Your workspace role does not have access to this action.")
        from admin_console.models import Subscription, TenantUsage
        subscription = membership.tenant.admin_subscriptions.select_related("plan").order_by("-created_at").first()
        request.subscription = subscription
        if subscription:
            path = request.path_info
            if subscription.status in {Subscription.Status.SUSPENDED, Subscription.Status.CHURNED}:
                raise PermissionDenied("This workspace is suspended. Contact KriyoPay support.")
            read_only = subscription.status in {Subscription.Status.PAST_DUE, Subscription.Status.CANCELLED, Subscription.Status.ONBOARDING}
            if subscription.status == Subscription.Status.TRIAL and subscription.trial_ends_at and subscription.trial_ends_at <= timezone.now():
                read_only = True
            is_billing_recovery = path.startswith("/api/v1/billing/razorpay/")
            if read_only and request.method not in SAFE_METHODS and not is_billing_recovery:
                raise PermissionDenied("This workspace is read-only. Review billing status or contact your administrator.")
            feature_key = None
            if request.method == "POST" and path.rstrip("/").endswith("/invoices"):
                feature_key = "invoice_upload"
            else:
                feature_routes = (
                    ("/api/v1/exports/tally-csv", "tally_csv_export"), ("/api/v1/tally-mappings", "tally_csv_export"),
                    ("/api/v1/ai-review/", "ai_extraction"),
                    ("/api/v1/purchase-orders", "po_grn_matching"), ("/api/v1/grns", "po_grn_matching"), ("/api/v1/matching/run", "po_grn_matching"),
                    ("/api/v1/duplicate-checks", "duplicate_detection"),
                    ("/api/v1/approval-rules", "approval_workflow"), ("/api/v1/approvals", "approval_workflow"), ("/api/v1/approval-delegations", "approval_workflow"),
                    ("/api/v1/auto-approval-rules", "auto_approval"), ("/api/v1/payments", "payment_tracking"), ("/api/v1/settlements/", "payment_tracking"), ("/api/v1/bank-reconciliation", "payment_tracking"),
                    ("/api/v1/fleet/", "fleet_management"),
                    ("/api/v1/credit-debit-notes", "credit_debit_notes"), ("/api/v1/custom-fields", "custom_fields"),
                    ("/api/v1/bulk-jobs", "bulk_actions"), ("/api/v1/whatsapp/", "whatsapp_intake"),
                    ("/api/v1/external/invoices", "api_access"), ("/api/v1/api-keys", "api_access"), ("/api/v1/webhooks", "api_access"), ("/api/v1/erp/", "api_access"),
                    ("/api/v1/reports/", "advanced_reports"), ("/api/v1/email-ingestion/logs", "email_invoice_intake"),
                )
                feature_key = next((key for route, key in feature_routes if path.startswith(route)), None)
                if path.endswith("/approval-history"):
                    feature_key = "approval_workflow"
            if path.startswith("/api/v1/invoices/") and request.method == "POST":
                invoice_action = path.rstrip("/").rsplit("/", 1)[-1]
                action_features = {
                    "extract": "ai_extraction", "confirm-extraction": "po_grn_matching",
                    "submit-for-approval": "approval_workflow", "approve": "approval_workflow",
                    "reject": "approval_workflow", "export": "tally_csv_export",
                    "resume-automation": "approval_workflow",
                }
                feature_key = action_features.get(invoice_action, feature_key)
            if feature_key:
                from admin_console.services import entitlements_for
                entitlement = entitlements_for(membership.tenant)["features"].get(feature_key)
                if not entitlement or not entitlement.get("enabled"):
                    raise PermissionDenied(f"Your current plan does not include {feature_key.replace('_', ' ')}.")
                if feature_key == "invoice_upload":
                    period_start = timezone.localdate().replace(day=1)
                    usage = TenantUsage.objects.filter(tenant=membership.tenant, period_start=period_start, metric="invoices_uploaded").values_list("used_count", flat=True).first() or 0
                    invoice_limit = entitlement.get("limit_value") or subscription.plan.invoice_limit
                    if invoice_limit is not None and usage >= invoice_limit:
                        raise PermissionDenied("Your monthly invoice limit has been reached. Contact your administrator to upgrade or request a temporary limit extension.")
        return True
