import secrets
import hashlib
from datetime import timedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Count, Sum, Q
from django.core.paginator import Paginator
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.text import slugify
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from accounts.models import Invitation, Membership
from tenants.models import Tenant
from .models import AdminAuditLog, AdminStaff, BillingInvoice, Feature, Payment, PaymentRefund, Plan, PlanFeature, Subscription, TenantFeatureOverride, TenantUsage
from accounts.permissions import HasTenantMembership
from .permissions import IsAdminStaff
from .serializers import AuditSerializer, BillingInvoiceSerializer, FeatureSerializer, PaymentSerializer, PlanSerializer, RefundSerializer, SubscriptionSerializer, TenantSerializer, UsageSerializer
from .services import entitlements_for
from .billing import GatewayError, GatewayUnavailable, activate_paid_subscription, gateway_configured, razorpay_request, verify_checkout_signature, verify_webhook_signature


def audit(request, action, tenant=None, obj=None, reason="", metadata=None):
    return AdminAuditLog.objects.create(actor=request.user, actor_role=request.admin_staff.role, action=action, tenant=tenant,
        object_type=obj.__class__.__name__ if obj else "", object_id=str(obj.pk) if obj else "", reason=reason, metadata=metadata or {})


class AdminMe(APIView):
    permission_classes = [IsAdminStaff]
    def get(self, request):
        return Response({"email": request.user.email, "name": request.user.get_full_name(), "role": request.admin_staff.role, "razorpay_configured": gateway_configured()})


class AdminDashboard(APIView):
    permission_classes = [IsAdminStaff]
    def get(self, request):
        tenants = Tenant.objects.filter(is_deleted=False)
        subscriptions = Subscription.objects.filter(tenant__is_deleted=False)
        current_month = timezone.localdate().replace(day=1)
        paid = Payment.objects.filter(status="PAID", paid_at__date__gte=current_month)
        summary = {
            "companies": tenants.count(),
            "active": subscriptions.filter(status="ACTIVE").count(),
            "trial": subscriptions.filter(status="TRIAL").count(),
            "past_due": subscriptions.filter(status__in=["PAST_DUE", "GRACE_PERIOD"]).count(),
            "suspended": subscriptions.filter(status="SUSPENDED").count(),
            "gateway_configured": gateway_configured(),
            "two_factor_enforced": False,
            "financial_access": request.admin_staff.role in {AdminStaff.Role.SUPER_ADMIN, AdminStaff.Role.ADMIN, AdminStaff.Role.BILLING_ADMIN},
        }
        if summary["financial_access"]:
            summary.update({
                "mrr_paise": sum((s.plan.monthly_price or 0) if s.billing_cycle == "MONTHLY" else (s.plan.annual_price or 0) // 12 if s.billing_cycle == "ANNUAL" else (s.plan.quarterly_price or 0) // 3 for s in subscriptions.filter(status="ACTIVE").select_related("plan")),
                "paid_this_month_paise": paid.aggregate(total=Sum("amount"))["total"] or 0,
                "failed_payments": Payment.objects.filter(status="FAILED").count(),
            })
        return Response(summary)


class CompanyListCreate(APIView):
    permission_classes = [IsAdminStaff]
    allowed_roles = [AdminStaff.Role.SUPER_ADMIN, AdminStaff.Role.ADMIN]
    def get(self, request):
        queryset = Tenant.objects.filter(is_deleted=False).annotate(owner_count=Count("memberships", filter=Q(memberships__role="OWNER"))).order_by("name")
        query = request.query_params.get("q")
        if query: queryset = queryset.filter(Q(name__icontains=query) | Q(workspace_key__icontains=query))
        try: page_size = min(100, max(1, int(request.query_params.get("page_size", 25))))
        except (TypeError, ValueError): return Response({"error": "page_size must be a number."}, status=400)
        paginator = Paginator(queryset, page_size)
        page = paginator.get_page(request.query_params.get("page", 1)) if paginator.count else None
        return Response({"results": TenantSerializer(page.object_list if page else [], many=True).data, "page": page.number if page else 1, "pages": paginator.num_pages, "total": paginator.count})

    @transaction.atomic
    def post(self, request):
        data = request.data
        required = ("company_name", "owner_name", "owner_email", "plan_id")
        missing = [key for key in required if not data.get(key)]
        if missing: return Response({"error": "Required fields: " + ", ".join(missing)}, status=400)
        User = get_user_model()
        email = str(data["owner_email"]).strip().lower()
        if User.objects.filter(email__iexact=email).exists(): return Response({"error": "Owner email already belongs to an account."}, status=400)
        plan = Plan.objects.filter(pk=data["plan_id"], is_active=True).first()
        if not plan: return Response({"error": "Select an active plan."}, status=400)
        billing_cycle = data.get("billing_cycle", Subscription.Cycle.MONTHLY)
        if billing_cycle not in Subscription.Cycle.values: return Response({"error": "Select a valid billing cycle."}, status=400)
        collect_payment = data.get("collect_payment", False)
        if not isinstance(collect_payment, bool):
            return Response({"error": "Collect payment must be true or false."}, status=400)
        if collect_payment:
            from .company_checkout import cycle_price
            if not gateway_configured():
                return Response({"error": "Configure Razorpay before selecting Collect payment now."}, status=503)
            if not cycle_price(plan, billing_cycle) or cycle_price(plan, billing_cycle) <= 0:
                return Response({"error": "Select a plan and billing cycle with a configured price."}, status=400)
        try: trial_days = max(1, min(int(data.get("trial_days", plan.trial_days or 14)), 365))
        except (TypeError, ValueError): return Response({"error": "Trial days must be a number between 1 and 365."}, status=400)
        base_slug = slugify(data.get("workspace_key") or data["company_name"])[:70] or "company"
        workspace_key, suffix = base_slug, 2
        while Tenant.objects.filter(workspace_key=workspace_key).exists():
            workspace_key = f"{base_slug[:70-len(str(suffix))-1]}-{suffix}"; suffix += 1
        owner_name = str(data["owner_name"]).strip()
        owner = User.objects.create(username=email, email=email, first_name=owner_name[:150])
        owner.set_unusable_password(); owner.save(update_fields=["password"])
        tenant_settings = {key: str(data[key]).strip() for key in ("phone", "gstin", "industry", "city", "state") if data.get(key)}
        tenant = Tenant.objects.create(name=str(data["company_name"])[:200], workspace_key=workspace_key, settings=tenant_settings)
        Membership.objects.create(tenant=tenant, user=owner, role=Membership.Role.OWNER)
        invite_token = secrets.token_urlsafe(32)
        invitation = Invitation.objects.create(tenant=tenant, email=email, role=Membership.Role.OWNER,
            token_hash=hashlib.sha256(invite_token.encode()).hexdigest(), expires_at=timezone.now()+timedelta(days=7), invited_by=request.user)
        accept_url = f"{settings.FRONTEND_BASE_URL}/invite/accept?token={invite_token}"
        sent_count = send_mail(f"Set up your KriyoPay account for {tenant.name}", f"Hello {owner_name},\n\nYour workspace has been created. Set your password and activate access here (link expires in 7 days):\n{accept_url}\n", settings.DEFAULT_FROM_EMAIL, [email], fail_silently=True)
        status_value = Subscription.Status.TRIAL if data.get("trial_enabled", True) and not collect_payment else Subscription.Status.ONBOARDING
        days = trial_days if status_value == Subscription.Status.TRIAL else None
        ends = timezone.now() + timedelta(days=days) if days else None
        sub = Subscription.objects.create(tenant=tenant, plan=plan, status=status_value, billing_cycle=billing_cycle, trial_ends_at=ends, current_period_end=ends)
        audit(request, "COMPANY_ONBOARDED", tenant, tenant, reason=str(data.get("notes", ""))[:500], metadata={"plan": plan.slug, "owner_email": email, "invitation_id": str(invitation.id), "invitation_email_sent": bool(sent_count)})
        delivery_status = "console_only" if settings.EMAIL_BACKEND.endswith("console.EmailBackend") else "submitted_to_email_backend" if sent_count else "not_submitted"
        return Response({"company": TenantSerializer(tenant).data, "subscription": SubscriptionSerializer(sub).data,
                         "owner_invitation": {"status": delivery_status, "email": email, "expires_at": invitation.expires_at}}, status=201)


class CompanyDetail(APIView):
    permission_classes = [IsAdminStaff]
    def get(self, request, tenant_id):
        tenant = Tenant.objects.filter(pk=tenant_id, is_deleted=False).first()
        if not tenant: return Response({"error": "Company not found."}, status=404)
        memberships = Membership.objects.filter(tenant=tenant).select_related("user")
        detail = {"company": TenantSerializer(tenant).data,
            "users": [{"email": m.user.email, "name": m.user.get_full_name(), "role": m.role, "active": m.is_active} for m in memberships],
            "subscriptions": SubscriptionSerializer(Subscription.objects.filter(tenant=tenant).select_related("plan"), many=True).data,
            "entitlements": entitlements_for(tenant),
            "usage": UsageSerializer(TenantUsage.objects.filter(tenant=tenant).order_by("-period_start"), many=True).data}
        if request.admin_staff.role in {AdminStaff.Role.SUPER_ADMIN, AdminStaff.Role.ADMIN, AdminStaff.Role.BILLING_ADMIN, AdminStaff.Role.READ_ONLY}:
            detail["audit"] = AuditSerializer(AdminAuditLog.objects.filter(tenant=tenant)[:30], many=True).data
        if request.admin_staff.role in {AdminStaff.Role.SUPER_ADMIN, AdminStaff.Role.ADMIN, AdminStaff.Role.BILLING_ADMIN}:
            detail["payments"] = PaymentSerializer(Payment.objects.filter(tenant=tenant).order_by("-created_at"), many=True).data
        return Response(detail)

    @transaction.atomic
    def delete(self, request, tenant_id):
        if request.admin_staff.role != AdminStaff.Role.SUPER_ADMIN:
            return Response({"error": "Only a Super Admin can delete a company."}, status=403)
        tenant = Tenant.objects.select_for_update().filter(pk=tenant_id, is_deleted=False).first()
        if not tenant: return Response({"error": "Company not found."}, status=404)
        confirmation = str(request.data.get("confirm_name", "")).strip()
        reason = str(request.data.get("reason", "")).strip()
        if confirmation != tenant.name or len(reason) < 8:
            return Response({"error": "Type the exact company name and provide a reason of at least 8 characters."}, status=400)
        memberships = Membership.objects.filter(tenant=tenant)
        audit(request, "COMPANY_DELETED", tenant, tenant, reason=reason[:500], metadata={"company_name": tenant.name, "workspace_key": tenant.workspace_key, "membership_count": memberships.count(), "retained_data": True})
        memberships.update(is_active=False)
        tenant.is_deleted = True
        tenant.deleted_at = timezone.now()
        tenant.save(update_fields=["is_deleted", "deleted_at"])
        return Response({"deleted": True, "retained_data": True})


class AdminPasswordChange(APIView):
    permission_classes = [IsAdminStaff]
    def post(self, request):
        current = request.data.get("current_password", "")
        new_password = request.data.get("new_password", "")
        if not request.user.check_password(current): return Response({"error": "Current password is incorrect."}, status=400)
        if not isinstance(new_password, str) or len(new_password) < 12:
            return Response({"error": "New password must be at least 12 characters."}, status=400)
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError
        try: validate_password(new_password, user=request.user)
        except ValidationError as exc: return Response({"error": " ".join(exc.messages)}, status=400)
        request.user.set_password(new_password)
        request.user.save(update_fields=["password"])
        audit(request, "ADMIN_PASSWORD_CHANGED", obj=request.user)
        return Response({"changed": True})


class SuperAdminCreate(APIView):
    permission_classes = [IsAdminStaff]
    allowed_roles = [AdminStaff.Role.SUPER_ADMIN]
    @transaction.atomic
    def post(self, request):
        email = str(request.data.get("email", "")).strip().lower()
        name = str(request.data.get("name", "")).strip()
        password = request.data.get("password", "")
        if not email or "@" not in email or not name:
            return Response({"error": "A valid email and name are required."}, status=400)
        if not isinstance(password, str) or len(password) < 12:
            return Response({"error": "Password must be at least 12 characters."}, status=400)
        User = get_user_model()
        if User.objects.filter(email__iexact=email).exists(): return Response({"error": "An account with this email already exists."}, status=400)
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError
        user = User(username=email, email=email, first_name=name[:150])
        try: validate_password(password, user=user)
        except ValidationError as exc: return Response({"error": " ".join(exc.messages)}, status=400)
        user.set_password(password); user.save()
        staff = AdminStaff.objects.create(user=user, role=AdminStaff.Role.SUPER_ADMIN)
        audit(request, "SUPER_ADMIN_CREATED", obj=staff, metadata={"email": email})
        return Response({"created": True, "email": email, "role": staff.role}, status=201)


class Plans(APIView):
    permission_classes = [IsAdminStaff]
    allowed_roles = [AdminStaff.Role.SUPER_ADMIN, AdminStaff.Role.ADMIN, AdminStaff.Role.BILLING_ADMIN]
    def get(self, request):
        return Response(PlanSerializer(Plan.objects.order_by("sort_order", "name"), many=True).data)
    def post(self, request):
        serializer = PlanSerializer(data=request.data)
        if not serializer.is_valid(): return Response(serializer.errors, status=400)
        plan = serializer.save(); audit(request, "PLAN_CREATED", obj=plan)
        return Response(serializer.data, status=201)


class PlanFeatures(APIView):
    permission_classes = [IsAdminStaff]
    allowed_roles = [AdminStaff.Role.SUPER_ADMIN, AdminStaff.Role.ADMIN, AdminStaff.Role.BILLING_ADMIN]
    def patch(self, request, plan_id):
        plan = Plan.objects.filter(pk=plan_id).first()
        if not plan: return Response({"error": "Plan not found."}, status=404)
        feature = Feature.objects.filter(key=request.data.get("feature_key"), is_active=True).first()
        if not feature or "enabled" not in request.data: return Response({"error": "Valid feature_key and enabled are required."}, status=400)
        row, _ = PlanFeature.objects.update_or_create(plan=plan, feature=feature, defaults={"enabled": bool(request.data["enabled"]), "limit_value": request.data.get("limit_value"), "limit_period": str(request.data.get("limit_period", ""))[:20]})
        audit(request, "PLAN_FEATURE_CHANGED", obj=row, metadata={"feature": feature.key, "enabled": row.enabled, "plan": plan.slug})
        return Response({"plan_id": str(plan.id), "feature_key": feature.key, "enabled": row.enabled, "limit_value": row.limit_value, "limit_period": row.limit_period})


class PlanDetail(APIView):
    permission_classes = [IsAdminStaff]
    allowed_roles = [AdminStaff.Role.SUPER_ADMIN, AdminStaff.Role.ADMIN, AdminStaff.Role.BILLING_ADMIN]
    def patch(self, request, plan_id):
        plan = Plan.objects.filter(pk=plan_id).first()
        if not plan: return Response({"error": "Plan not found."}, status=404)
        serializer = PlanSerializer(plan, data=request.data, partial=True)
        if not serializer.is_valid(): return Response(serializer.errors, status=400)
        plan = serializer.save(); audit(request, "PLAN_UPDATED", obj=plan, metadata={"fields": list(request.data.keys())})
        return Response(serializer.data)


class Features(APIView):
    permission_classes = [IsAdminStaff]
    def get(self, request):
        features = FeatureSerializer(Feature.objects.order_by("sort_order", "name"), many=True).data
        plan_rows = PlanFeature.objects.select_related("plan", "feature")
        return Response({"features": features, "plan_entitlements": [{"plan_id": row.plan_id, "feature_key": row.feature.key, "enabled": row.enabled, "limit_value": row.limit_value, "limit_period": row.limit_period} for row in plan_rows]})


class Subscriptions(APIView):
    permission_classes = [IsAdminStaff]
    def get(self, request):
        return Response(SubscriptionSerializer(Subscription.objects.select_related("tenant", "plan").order_by("-created_at"), many=True).data)


class Usage(APIView):
    permission_classes = [IsAdminStaff]
    def get(self, request):
        rows = TenantUsage.objects.select_related("tenant").order_by("-period_start")
        if request.query_params.get("tenant"): rows = rows.filter(tenant_id=request.query_params["tenant"])
        return Response(UsageSerializer(rows, many=True).data)


class Payments(APIView):
    permission_classes = [IsAdminStaff]
    allowed_roles = [AdminStaff.Role.SUPER_ADMIN, AdminStaff.Role.ADMIN, AdminStaff.Role.BILLING_ADMIN]
    def get(self, request):
        return Response({"gateway_configured": gateway_configured(), "results": PaymentSerializer(Payment.objects.select_related("tenant").order_by("-created_at"), many=True).data})


class OfflinePaymentRecord(APIView):
    permission_classes = [IsAdminStaff]
    allowed_roles = [AdminStaff.Role.SUPER_ADMIN, AdminStaff.Role.BILLING_ADMIN]
    def post(self, request):
        tenant = Tenant.objects.filter(pk=request.data.get("tenant_id")).first()
        if not tenant: return Response({"error": "Company not found."}, status=404)
        subscription = tenant.admin_subscriptions.select_related("plan").order_by("-created_at").first()
        if not subscription: return Response({"error": "Create a subscription before recording payment."}, status=409)
        plan = Plan.objects.filter(pk=request.data.get("plan_id") or subscription.plan_id, is_active=True).first()
        cycle = request.data.get("billing_cycle", subscription.billing_cycle)
        reason = str(request.data.get("reason", "")).strip()
        reference = str(request.data.get("reference", "")).strip()
        method = str(request.data.get("payment_method", "BANK_TRANSFER")).strip().upper()
        try: amount = int(request.data.get("amount", 0))
        except (TypeError, ValueError): return Response({"error": "amount must be an integer number of paise."}, status=400)
        if not plan or cycle not in Subscription.Cycle.values or amount <= 0 or not reason or not reference:
            return Response({"error": "A valid plan, billing cycle, positive amount in paise, payment reference, and reason are required."}, status=400)
        if method not in {"BANK_TRANSFER", "NEFT", "RTGS", "IMPS", "CHEQUE", "UPI_OFFLINE"}:
            return Response({"error": "Choose a supported offline payment method."}, status=400)
        payment = Payment.objects.create(tenant=tenant, subscription=subscription, requested_plan=plan, billing_cycle=cycle,
            amount=amount, currency=plan.currency, status=Payment.Status.PENDING, payment_method=method, offline_reference=reference[:120])
        activate_paid_subscription(payment, {"source": "admin_offline_payment", "reference": reference[:120], "method": method})
        audit(request, "OFFLINE_PAYMENT_RECORDED", tenant, payment, reason=reason[:500], metadata={"amount_paise": amount, "method": method, "reference": reference[:120]})
        return Response(PaymentSerializer(payment).data, status=201)


class Refunds(APIView):
    permission_classes = [IsAdminStaff]
    allowed_roles = [AdminStaff.Role.SUPER_ADMIN, AdminStaff.Role.ADMIN, AdminStaff.Role.BILLING_ADMIN]
    def get(self, request):
        if request.query_params.get("intents") == "1":
            from .models import RefundIntent
            return Response([{
                "id": str(row.pk), "tenant_name": row.payment.tenant.name,
                "payment": str(row.payment_id), "request_key": str(row.request_key),
                "amount": row.amount, "status": row.status, "reason": row.reason,
                "created_at": row.created_at,
                "razorpay_refund_id": row.refund.razorpay_refund_id if row.refund_id else None,
            } for row in RefundIntent.objects.select_related("payment__tenant", "refund").order_by("-created_at")[:200]])
        return Response(RefundSerializer(PaymentRefund.objects.select_related("tenant", "payment").order_by("-created_at"), many=True).data)


class PaymentRefundCreate(APIView):
    permission_classes = [IsAdminStaff]
    allowed_roles = [AdminStaff.Role.SUPER_ADMIN, AdminStaff.Role.BILLING_ADMIN]
    def get(self, request, payment_id):
        from .models import RefundIntent
        if not Payment.objects.filter(pk=payment_id).exists():
            return Response({"error": "Payment not found."}, status=404)
        return Response({"intents": [{
            "intent_id": str(row.pk), "idempotency_key": str(row.request_key),
            "amount": row.amount, "requested_amount": row.requested_amount, "reason": row.reason,
            "status": row.status, "created_at": row.created_at,
            "razorpay_refund_id": row.refund.razorpay_refund_id if row.refund_id else None,
        } for row in RefundIntent.objects.filter(payment_id=payment_id).select_related("refund").order_by("-created_at")[:100]]})
    def post(self, request, payment_id):
        payment = Payment.objects.filter(pk=payment_id).first()
        if not payment: return Response({"error": "Payment not found."}, status=404)
        if not gateway_configured(): return Response({"error": "Razorpay is not configured."}, status=503)
        from .refunds import reserve, execute
        intent = reserve(payment.pk, request.user, request.data.get("amount"), request.data.get("reason"),
                         request.data.get("idempotency_key") or request.headers.get("Idempotency-Key"))
        intent = execute(intent, razorpay_request)
        result = RefundSerializer(intent.refund).data if intent.refund_id else {}
        result.update({"intent_id": str(intent.pk), "idempotency_key": str(intent.request_key), "status": intent.status,
                       "message": "Refund outcome is being checked. Retry this same request to check status; do not create another refund."
                       if intent.status in {"UNKNOWN", "SUBMITTING"} else "Refund status recorded."})
        return Response(result, status=202 if not intent.refund_id else 201)



class TenantBillingSummary(APIView):
    permission_classes = [HasTenantMembership]
    def get(self, request):
        subscription = request.tenant.admin_subscriptions.select_related("plan").order_by("-created_at").first()
        current_period = timezone.localdate().replace(day=1)
        usage = TenantUsage.objects.filter(tenant=request.tenant, period_start=current_period).order_by("metric")
        return Response({
            "subscription": SubscriptionSerializer(subscription).data if subscription else None,
            "plan": PlanSerializer(subscription.plan).data if subscription else None,
            "usage": UsageSerializer(usage, many=True).data,
            "available_plans": PlanSerializer(Plan.objects.filter(is_active=True, is_public=True).order_by("sort_order"), many=True).data,
            "billing_invoices": BillingInvoiceSerializer(BillingInvoice.objects.filter(tenant=request.tenant).order_by("-created_at")[:50], many=True).data,
            "payments": PaymentSerializer(Payment.objects.filter(tenant=request.tenant).order_by("-created_at")[:50], many=True).data,
            "gateway_configured": gateway_configured(),
        })


class RazorpayCreateOrder(APIView):
    permission_classes = [HasTenantMembership]
    def post(self, request):
        if request.membership.role not in (Membership.Role.OWNER, Membership.Role.FINANCE):
            return Response({"error": "Workspace owner or finance role required."}, status=403)
        if not gateway_configured(): return Response({"error": "Razorpay is not configured. Checkout is unavailable."}, status=503)
        subscription = request.tenant.admin_subscriptions.select_related("plan").order_by("-created_at").first()
        if not subscription: return Response({"error": "This workspace does not have a billable subscription."}, status=409)
        plan = Plan.objects.filter(pk=request.data.get("plan_id"), is_active=True, is_public=True).first()
        cycle = request.data.get("billing_cycle", subscription.billing_cycle)
        if not plan or cycle not in Subscription.Cycle.values: return Response({"error": "Select a valid active plan and billing cycle."}, status=400)
        amount = {Subscription.Cycle.MONTHLY: plan.monthly_price, Subscription.Cycle.QUARTERLY: plan.quarterly_price, Subscription.Cycle.ANNUAL: plan.annual_price}[cycle]
        if amount is None or amount <= 0: return Response({"error": "Contact KriyoPay billing for custom pricing."}, status=400)
        pending = Payment.objects.filter(tenant=request.tenant, subscription=subscription, requested_plan=plan, billing_cycle=cycle, status=Payment.Status.PENDING).order_by("-created_at").first()
        if pending:
            return Response({"payment_id": str(pending.id), "order_id": pending.razorpay_order_id, "amount": pending.amount,
                "currency": pending.currency, "key_id": settings.RAZORPAY_KEY_ID, "company_name": request.tenant.name}, status=200)
        receipt = f"KP{secrets.token_hex(18)}"[:40]
        try:
            order = razorpay_request("POST", "/orders", {"amount": amount, "currency": plan.currency, "receipt": receipt,
                "notes": {"tenant_id": str(request.tenant.id), "subscription_id": str(subscription.id), "plan_id": str(plan.id), "billing_cycle": cycle}})
        except GatewayUnavailable as error: return Response({"error": str(error)}, status=503)
        except GatewayError: return Response({"error": "Razorpay order creation failed. Please retry or contact billing support."}, status=502)
        if order.get("amount") != amount or order.get("currency") != plan.currency or not order.get("id"):
            return Response({"error": "Razorpay returned an order that does not match the requested amount."}, status=502)
        payment = Payment.objects.create(tenant=request.tenant, subscription=subscription, requested_plan=plan, billing_cycle=cycle,
            razorpay_order_id=order["id"], amount=amount, currency=plan.currency, status=Payment.Status.PENDING)
        return Response({"payment_id": str(payment.id), "order_id": order["id"], "amount": amount, "currency": plan.currency,
            "key_id": settings.RAZORPAY_KEY_ID, "company_name": request.tenant.name}, status=201)


class RazorpayVerifyPayment(APIView):
    permission_classes = [HasTenantMembership]
    def post(self, request):
        if request.membership.role not in (Membership.Role.OWNER, Membership.Role.FINANCE):
            return Response({"error": "Workspace owner or finance role required."}, status=403)
        order_id = str(request.data.get("razorpay_order_id", ""))
        payment_id = str(request.data.get("razorpay_payment_id", ""))
        signature = str(request.data.get("razorpay_signature", ""))
        payment = Payment.objects.select_related("subscription", "requested_plan").filter(tenant=request.tenant, razorpay_order_id=order_id).first()
        if not payment: return Response({"error": "Payment order not found."}, status=404)
        if payment.status == Payment.Status.PAID: return Response({"status": "PAID", "subscription": SubscriptionSerializer(payment.subscription).data})
        if not verify_checkout_signature(order_id, payment_id, signature):
            AdminAuditLog.objects.create(actor=request.user, actor_role="TENANT_"+request.membership.role, action="RAZORPAY_SIGNATURE_REJECTED", tenant=request.tenant, object_type="Payment", object_id=str(payment.id))
            return Response({"error": "Payment signature could not be verified."}, status=400)
        try:
            remote = razorpay_request("GET", f"/payments/{payment_id}")
        except GatewayUnavailable as error: return Response({"error": str(error)}, status=503)
        except GatewayError: return Response({"error": "Could not verify payment status with Razorpay. It remains pending."}, status=502)
        if remote.get("order_id") != payment.razorpay_order_id or remote.get("amount") != payment.amount or remote.get("currency") != payment.currency or remote.get("status") != "captured":
            return Response({"error": "Razorpay has not confirmed a captured payment for the expected order amount."}, status=409)
        payment.razorpay_payment_id = payment_id
        payment.razorpay_signature = signature
        activate_paid_subscription(payment, {"source": "verified_checkout", "payment_id": payment_id, "order_id": order_id})
        return Response({"status": "PAID", "subscription": SubscriptionSerializer(payment.subscription).data})


class RazorpayWebhook(APIView):
    authentication_classes = []
    permission_classes = []
    def post(self, request):
        if not settings.RAZORPAY_WEBHOOK_SECRET:
            return Response({"error": "Razorpay webhook is not configured."}, status=503)
        raw = request.body
        signature = request.headers.get("X-Razorpay-Signature", "")
        if not verify_webhook_signature(raw, signature): return Response({"error": "Invalid Razorpay webhook signature."}, status=400)
        try: payload = __import__("json").loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError): return Response({"error": "Invalid webhook JSON."}, status=400)
        if not isinstance(payload, dict):
            return Response({"error": "Webhook payload must be an object."}, status=400)
        event_type = str(payload.get("event", ""))[:80]
        if event_type not in {"payment.captured", "payment.failed", "order.paid", "refund.processed", "refund.failed"}:
            return Response({"status": "ignored"}, status=200)
        from .models import RazorpayWebhookEvent
        event_id = request.headers.get("X-Razorpay-Event-Id") or hashlib.sha256(raw).hexdigest()
        event_id = event_id[:160]
        event, created = RazorpayWebhookEvent.objects.get_or_create(event_id=event_id, defaults={"event_type": event_type, "payload": payload})
        # A verified event ID is immutable. Do not replace a prior event's payload.
        if not created and event.payload != payload:
            return Response({"error": "Event ID already belongs to a different payload."}, status=409)
        from .webhook_recovery import publish_event
        published = publish_event(event.id)
        if published is False:
            return Response({"error": "Event saved; queue recovery is scheduled."}, status=503)
        return Response({"status": "accepted" if published else "already queued or processed"}, status=202 if published else 200)



class BillingInvoices(APIView):
    permission_classes = [IsAdminStaff]
    allowed_roles = [AdminStaff.Role.SUPER_ADMIN, AdminStaff.Role.ADMIN, AdminStaff.Role.BILLING_ADMIN]
    def get(self, request):
        return Response(BillingInvoiceSerializer(BillingInvoice.objects.select_related("tenant").order_by("-created_at"), many=True).data)


class AuditLogs(APIView):
    permission_classes = [IsAdminStaff]
    allowed_roles = [AdminStaff.Role.SUPER_ADMIN, AdminStaff.Role.ADMIN, AdminStaff.Role.BILLING_ADMIN, AdminStaff.Role.READ_ONLY]
    def get(self, request):
        rows = AdminAuditLog.objects.select_related("actor", "tenant").all()
        if request.query_params.get("tenant"): rows = rows.filter(tenant_id=request.query_params["tenant"])
        return Response(AuditSerializer(rows[:500], many=True).data)


class RazorpayEvents(APIView):
    permission_classes = [IsAdminStaff]
    allowed_roles = [AdminStaff.Role.SUPER_ADMIN, AdminStaff.Role.ADMIN, AdminStaff.Role.BILLING_ADMIN]
    def get(self, request):
        from .models import RazorpayWebhookEvent
        events = RazorpayWebhookEvent.objects.all()[:500]
        return Response([{"event_id": row.event_id, "event_type": row.event_type, "status": row.status,
            "attempt_count": row.attempt_count, "error_message": row.error_message, "received_at": row.received_at,
            "processed_at": row.processed_at} for row in events])


class CompanyLifecycle(APIView):
    permission_classes = [IsAdminStaff]
    allowed_roles = [AdminStaff.Role.SUPER_ADMIN, AdminStaff.Role.ADMIN, AdminStaff.Role.BILLING_ADMIN]
    valid = {choice for choice, _ in Subscription.Status.choices}
    def post(self, request, tenant_id):
        tenant = Tenant.objects.filter(pk=tenant_id).first()
        if not tenant: return Response({"error": "Company not found."}, status=404)
        state, reason = request.data.get("status"), str(request.data.get("reason", "")).strip()
        if state not in self.valid or not reason: return Response({"error": "A valid status and reason are required."}, status=400)
        sub = Subscription.objects.filter(tenant=tenant).order_by("-created_at").first()
        if not sub: return Response({"error": "No subscription exists."}, status=404)
        old = sub.status; sub.status = state; sub.save(update_fields=["status", "updated_at"])
        audit(request, "COMPANY_LIFECYCLE_CHANGED", tenant, sub, reason=reason[:500], metadata={"from": old, "to": state})
        return Response(SubscriptionSerializer(sub).data)


class CompanyEntitlements(APIView):
    permission_classes = [IsAdminStaff]
    allowed_roles = [AdminStaff.Role.SUPER_ADMIN, AdminStaff.Role.ADMIN]
    def get(self, request, tenant_id):
        tenant = Tenant.objects.filter(pk=tenant_id).first()
        if not tenant: return Response({"error": "Company not found."}, status=404)
        return Response(entitlements_for(tenant))
    def patch(self, request, tenant_id):
        tenant = Tenant.objects.filter(pk=tenant_id).first()
        if not tenant: return Response({"error": "Company not found."}, status=404)
        feature = Feature.objects.filter(key=request.data.get("feature_key"), is_active=True).first()
        reason = str(request.data.get("reason", "")).strip()
        if not feature or not reason or "enabled" not in request.data: return Response({"error": "feature_key, enabled, and reason are required."}, status=400)
        raw_limit = request.data.get("limit_value")
        try: limit = int(raw_limit) if raw_limit not in (None, "") else None
        except (TypeError, ValueError): return Response({"error": "limit_value must be a non-negative integer."}, status=400)
        if limit is not None and limit < 0: return Response({"error": "limit_value must be a non-negative integer."}, status=400)
        raw_expiry = request.data.get("expires_at") or None
        expiry = parse_datetime(raw_expiry) if isinstance(raw_expiry, str) else raw_expiry
        if raw_expiry and not expiry: return Response({"error": "expires_at must be a valid ISO datetime."}, status=400)
        if expiry and timezone.is_naive(expiry): return Response({"error": "expires_at must include a timezone."}, status=400)
        raw_enabled = request.data["enabled"]
        if isinstance(raw_enabled, bool): enabled = raw_enabled
        elif isinstance(raw_enabled, str) and raw_enabled.lower() in {"true", "false"}: enabled = raw_enabled.lower() == "true"
        else: return Response({"error": "enabled must be a boolean."}, status=400)
        override = TenantFeatureOverride.objects.create(tenant=tenant, feature=feature, enabled=enabled, limit_value=limit, reason=reason[:500], created_by=request.user, expires_at=expiry)
        audit(request, "TENANT_ENTITLEMENT_OVERRIDDEN", tenant, override, reason=reason, metadata={"feature": feature.key, "enabled": override.enabled, "expires_at": str(override.expires_at) if override.expires_at else None})
        return Response(entitlements_for(tenant))
