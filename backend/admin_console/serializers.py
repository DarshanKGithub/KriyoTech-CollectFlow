from rest_framework import serializers
from tenants.models import Tenant
from .models import AdminAuditLog, BillingInvoice, Feature, Payment, PaymentRefund, Plan, PlanFeature, Subscription, TenantUsage


class TenantSerializer(serializers.ModelSerializer):
    owner_email = serializers.SerializerMethodField()
    subscription_status = serializers.SerializerMethodField()
    def get_subscription_status(self, tenant):
        return tenant.admin_subscriptions.order_by("-created_at").values_list("status", flat=True).first()
    def get_owner_email(self, tenant):
        owner = tenant.memberships.filter(role="OWNER").select_related("user").first()
        return owner.user.email if owner else None
    class Meta:
        model = Tenant
        fields = ["id", "name", "workspace_key", "created_at", "owner_email", "subscription_status"]


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]


class FeatureSerializer(serializers.ModelSerializer):
    class Meta:
        model = Feature
        fields = "__all__"


class SubscriptionSerializer(serializers.ModelSerializer):
    tenant_name = serializers.CharField(source="tenant.name", read_only=True)
    plan_name = serializers.CharField(source="plan.name", read_only=True)
    class Meta:
        model = Subscription
        fields = "__all__"


class UsageSerializer(serializers.ModelSerializer):
    tenant_name = serializers.CharField(source="tenant.name", read_only=True)
    class Meta:
        model = TenantUsage
        fields = "__all__"


class PaymentSerializer(serializers.ModelSerializer):
    tenant_name = serializers.CharField(source="tenant.name", read_only=True)
    class Meta:
        model = Payment
        exclude = ["failure_reason", "raw_webhook_payload", "razorpay_signature"]


class RefundSerializer(serializers.ModelSerializer):
    tenant_name = serializers.CharField(source="tenant.name", read_only=True)
    payment_order_id = serializers.CharField(source="payment.razorpay_order_id", read_only=True)
    payment_id = serializers.CharField(source="payment.razorpay_payment_id", read_only=True)
    class Meta:
        model = PaymentRefund
        exclude = ["raw_gateway_payload"]


class BillingInvoiceSerializer(serializers.ModelSerializer):
    tenant_name = serializers.CharField(source="tenant.name", read_only=True)
    class Meta:
        model = BillingInvoice
        fields = "__all__"


class AuditSerializer(serializers.ModelSerializer):
    actor_email = serializers.EmailField(source="actor.email", read_only=True)
    tenant_name = serializers.CharField(source="tenant.name", read_only=True)
    class Meta:
        model = AdminAuditLog
        fields = "__all__"
