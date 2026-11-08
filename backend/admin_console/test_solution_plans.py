from io import StringIO
import pytest
from django.core.management import call_command
from .models import AdminAuditLog, Feature, Plan, PlanFeature
from .launch_pricing import PLAN_PRICES


@pytest.mark.django_db
def test_solution_package_prices_and_access_are_explicit_and_replay_safe():
    Feature.objects.get_or_create(key="payment_tracking", defaults={"name": "Payment tracking"})
    call_command("seed_solution_plans", stdout=StringIO())
    for slug in ("reconcile", "settleview", "transport", "driverfinance"):
        plan = Plan.objects.get(slug=slug)
        assert (plan.monthly_price, plan.quarterly_price, plan.annual_price) == PLAN_PRICES[slug]
        assert plan.user_limit == 5 and plan.invoice_limit == 0
    enabled = lambda slug: set(PlanFeature.objects.filter(plan__slug=slug, enabled=True).values_list("feature__key", flat=True))
    assert enabled("reconcile") == {"payment_tracking"}
    assert enabled("settleview") == {"payment_tracking", "settlement_review"}
    assert "fleet_fuel" in enabled("transport") and "fleet_driver_finance" not in enabled("transport")
    assert enabled("driverfinance") == {"fleet_management", "fleet_driver_finance", "fleet_customer_billing", "fleet_freight_reconciliation"}
    assert AdminAuditLog.objects.filter(action="SOLUTION_PLAN_CREATED").count() == 4
    plan = Plan.objects.get(slug="transport")
    plan.monthly_price = 123400; plan.save(update_fields=["monthly_price"])
    PlanFeature.objects.filter(plan=plan, feature__key="fleet_fuel").update(enabled=False)
    call_command("seed_solution_plans", stdout=StringIO())
    plan.refresh_from_db()
    assert plan.monthly_price == 123400
    assert not PlanFeature.objects.get(plan=plan, feature__key="fleet_fuel").enabled
    assert AdminAuditLog.objects.filter(action="SOLUTION_PLAN_CREATED").count() == 4
