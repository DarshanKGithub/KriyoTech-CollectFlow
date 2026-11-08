from io import StringIO
import pytest
from django.core.management import call_command
from tenants.models import Tenant
from .models import AdminAuditLog, BillingInvoice, Feature, Payment, Plan, PlanFeature, Subscription
from .launch_pricing import PLAN_PRICES


@pytest.mark.django_db
def test_launch_price_review_is_previewable_audited_and_preserves_financial_history():
    plan = Plan.objects.create(name="Starter", slug="starter", monthly_price=750000, annual_price=7500000)
    custom = Plan.objects.create(name="Negotiated", slug="negotiated", monthly_price=123456)
    tenant = Tenant.objects.create(name="Price review", workspace_key="price-review")
    subscription = Subscription.objects.create(tenant=tenant, plan=plan, status="ACTIVE")
    feature = Feature.objects.get(key="fleet_fuel")
    feature.monthly_price = 99900; feature.save(update_fields=["monthly_price"])
    grant = PlanFeature.objects.create(plan=plan, feature=feature, enabled=False)
    pending = Payment.objects.create(tenant=tenant, subscription=subscription, requested_plan=plan,
        amount=750000, status="PENDING", razorpay_order_id="order_price_review")
    invoice = BillingInvoice.objects.create(tenant=tenant, subscription=subscription, invoice_number="PRICE-REVIEW-1",
        plan_name="Starter", billing_period_start="2026-11-01", billing_period_end="2026-12-01",
        base_amount=750000, total_amount=750000, status="PAID")
    call_command("apply_launch_pricing", stdout=StringIO())
    plan.refresh_from_db(); feature.refresh_from_db()
    assert plan.monthly_price == 750000 and feature.monthly_price == 99900
    assert not AdminAuditLog.objects.filter(action="PLAN_PRICING_REVIEW_APPLIED").exists()

    call_command("apply_launch_pricing", apply=True, stdout=StringIO())
    plan.refresh_from_db(); feature.refresh_from_db(); custom.refresh_from_db()
    pending.refresh_from_db(); invoice.refresh_from_db(); subscription.refresh_from_db(); grant.refresh_from_db()
    assert (plan.monthly_price, plan.quarterly_price, plan.annual_price) == PLAN_PRICES["starter"]
    assert feature.monthly_price == 29900 and feature.price_basis == "COMPANY"
    assert custom.monthly_price == 123456
    assert pending.amount == 750000 and pending.status == "PENDING"
    assert invoice.total_amount == 750000 and invoice.status == "PAID"
    assert subscription.status == "ACTIVE" and subscription.plan_id == plan.id
    assert grant.enabled is False
    audit_count = AdminAuditLog.objects.filter(action__in=["PLAN_PRICING_REVIEW_APPLIED", "FEATURE_PRICING_REVIEW_APPLIED"]).count()
    assert audit_count >= 2
    call_command("apply_launch_pricing", apply=True, stdout=StringIO())
    assert AdminAuditLog.objects.filter(action__in=["PLAN_PRICING_REVIEW_APPLIED", "FEATURE_PRICING_REVIEW_APPLIED"]).count() == audit_count
