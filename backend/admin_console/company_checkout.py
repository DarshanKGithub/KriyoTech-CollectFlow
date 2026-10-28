"""Staff-assisted checkout for a company's initial subscription."""
import secrets

from django.conf import settings
from django.db import transaction
from rest_framework.response import Response
from rest_framework.views import APIView

from tenants.models import Tenant
from .billing import (GatewayError, GatewayUnavailable, activate_paid_subscription,
                      gateway_configured, razorpay_request, verify_checkout_signature)
from .models import AdminAuditLog, AdminStaff, Payment, Subscription
from .permissions import IsAdminStaff


def cycle_price(plan, cycle):
    return {"MONTHLY": plan.monthly_price, "QUARTERLY": plan.quarterly_price,
            "ANNUAL": plan.annual_price}.get(cycle)


class CompanyCheckout(APIView):
    permission_classes = [IsAdminStaff]
    allowed_roles = [AdminStaff.Role.SUPER_ADMIN, AdminStaff.Role.ADMIN, AdminStaff.Role.BILLING_ADMIN]

    def get(self, request, tenant_id):
        tenant = Tenant.objects.filter(pk=tenant_id, is_deleted=False).first()
        if not tenant:
            return Response({"error": "Company not found."}, status=404)
        subscription = tenant.admin_subscriptions.order_by("-created_at").first()
        payment = Payment.objects.filter(subscription=subscription, tenant=tenant).order_by("-created_at").first() if subscription else None
        return Response({"subscription_status": subscription.status if subscription else None,
            "payment_status": payment.status if payment else None,
            "paid": bool(subscription and subscription.status == Subscription.Status.ACTIVE and payment and payment.status == Payment.Status.PAID)})

    @transaction.atomic
    def post(self, request, tenant_id):
        tenant = Tenant.objects.select_for_update().filter(pk=tenant_id, is_deleted=False).first()
        if not tenant:
            return Response({"error": "Company not found."}, status=404)
        subscription = tenant.admin_subscriptions.select_related("plan").order_by("-created_at").first()
        if not subscription or subscription.status not in {Subscription.Status.ONBOARDING, Subscription.Status.TRIAL}:
            return Response({"error": "Initial checkout is available for companies awaiting activation or on trial."}, status=409)
        if not gateway_configured():
            return Response({"error": "Configure Razorpay API credentials before collecting payment."}, status=503)
        plan = subscription.plan
        amount = cycle_price(plan, subscription.billing_cycle)
        if not plan.is_active or not amount or amount <= 0:
            return Response({"error": "This plan and billing cycle need a positive configured price."}, status=400)
        # A tenant lock serializes repeated clicks. Reuse the order even if its price
        # was subsequently edited: the stored order remains the customer's quote.
        payment = Payment.objects.filter(subscription=subscription, requested_plan=plan,
            billing_cycle=subscription.billing_cycle, status=Payment.Status.PENDING).exclude(razorpay_order_id="").order_by("-created_at").first()
        created = payment is None
        if created:
            try:
                order = razorpay_request("POST", "/orders", {"amount": amount, "currency": plan.currency,
                    "receipt": f"KP{secrets.token_hex(18)}", "notes": {"tenant_id": str(tenant.id),
                    "subscription_id": str(subscription.id), "plan_id": str(plan.id), "billing_cycle": subscription.billing_cycle}})
            except GatewayUnavailable:
                return Response({"error": "Razorpay is not configured."}, status=503)
            except GatewayError:
                return Response({"error": "Could not open Razorpay checkout. Company is saved; retry payment."}, status=502)
            if order.get("amount") != amount or order.get("currency") != plan.currency or not order.get("id"):
                return Response({"error": "Razorpay returned an invalid order. Payment was not recorded."}, status=502)
            payment = Payment.objects.create(tenant=tenant, subscription=subscription, requested_plan=plan,
                billing_cycle=subscription.billing_cycle, razorpay_order_id=order["id"], amount=amount,
                currency=plan.currency, payment_method="RAZORPAY")
            AdminAuditLog.objects.create(actor=request.user, actor_role=request.admin_staff.role,
                action="COMPANY_CHECKOUT_CREATED", tenant=tenant, object_type="Payment", object_id=str(payment.id))
        owner = tenant.memberships.filter(role="OWNER", is_active=True).select_related("user").first()
        return Response({"payment_id": str(payment.id), "order_id": payment.razorpay_order_id,
            "amount": payment.amount, "currency": payment.currency, "key_id": settings.RAZORPAY_KEY_ID,
            "company_name": tenant.name, "plan_name": plan.name, "billing_cycle": subscription.billing_cycle,
            "prefill": {"name": owner.user.get_full_name() if owner else "", "email": owner.user.email if owner else ""}}, status=201 if created else 200)


class CompanyCheckoutVerify(APIView):
    permission_classes = [IsAdminStaff]
    allowed_roles = CompanyCheckout.allowed_roles

    def post(self, request, tenant_id):
        order_id = str(request.data.get("razorpay_order_id", ""))
        payment_id = str(request.data.get("razorpay_payment_id", ""))
        signature = str(request.data.get("razorpay_signature", ""))
        if not order_id or not payment_id or not signature:
            return Response({"error": "Order, payment ID and signature are required."}, status=400)
        payment = Payment.objects.filter(tenant_id=tenant_id, tenant__is_deleted=False, razorpay_order_id=order_id).first()
        if not payment:
            return Response({"error": "Payment order not found for this company."}, status=404)
        if not verify_checkout_signature(payment.razorpay_order_id, payment_id, signature):
            return Response({"error": "Payment signature could not be verified."}, status=400)
        if payment.status in {Payment.Status.REFUNDED, Payment.Status.PARTIALLY_REFUNDED}:
            return Response({"error": "This payment has already been refunded."}, status=409)
        if payment.status == Payment.Status.PAID:
            return Response({"status": "PAID"})
        try:
            remote = razorpay_request("GET", f"/payments/{payment_id}")
        except (GatewayError, GatewayUnavailable):
            return Response({"error": "Payment is awaiting server verification. Do not pay again; check Payments shortly."}, status=502)
        if (remote.get("id") != payment_id or remote.get("order_id") != payment.razorpay_order_id
                or remote.get("amount") != payment.amount or remote.get("currency") != payment.currency
                or remote.get("status") != "captured"):
            return Response({"error": "Razorpay has not confirmed the captured payment. Check Payments shortly before retrying."}, status=409)
        payment.razorpay_payment_id = payment_id
        payment.razorpay_signature = signature
        activate_paid_subscription(payment, {"source": "admin_company_checkout", "payment_id": payment_id, "order_id": order_id})
        return Response({"status": "PAID"})
