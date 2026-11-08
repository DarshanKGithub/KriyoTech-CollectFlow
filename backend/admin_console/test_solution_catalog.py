import pytest
from rest_framework.test import APIClient
from accounts.models import User, Membership
from tenants.models import Tenant
from .models import AdminStaff, AdminAuditLog, Feature, Plan, PlanFeature, Subscription
from .services import entitlements_for
from .test_helpers import authenticate_staff


@pytest.fixture
def commercial(db):
    user = User.objects.create_user(username="catalog-super", email="catalog-super@example.test")
    staff = AdminStaff.objects.create(user=user, role="SUPER_ADMIN")
    client = APIClient()
    authenticate_staff(client, staff)
    tenant = Tenant.objects.create(name="Catalog Fleet", workspace_key="catalog-fleet")
    plan = Plan.objects.create(name="Catalog plan", slug="catalog-plan", monthly_price=10000)
    Subscription.objects.create(tenant=tenant, plan=plan, status="ACTIVE")
    master = Feature.objects.get(key="fleet_management")
    PlanFeature.objects.create(plan=plan, feature=master, enabled=True)
    return client, staff, tenant, plan


def test_pricing_update_is_audited_and_does_not_change_plan_or_access(commercial):
    client, staff, tenant, plan = commercial
    feature = Feature.objects.get(key="fleet_fuel")
    response = client.patch(f"/api/v1/admin/features/{feature.key}/pricing", {
        "solution_name": "Transport", "monthly_price": 79900, "price_basis": "COMPANY",
        "reason": "Set initial fuel catalog price",
    }, format="json")
    assert response.status_code == 200, response.data
    feature.refresh_from_db(); plan.refresh_from_db()
    assert feature.monthly_price == 79900
    assert plan.monthly_price == 10000
    assert entitlements_for(tenant)["features"]["fleet_fuel"]["enabled"] is True
    log = AdminAuditLog.objects.get(action="FEATURE_PRICING_UPDATED")
    assert log.actor_id == staff.user_id and log.metadata["after"]["monthly_price"] == 79900


@pytest.mark.parametrize("price", [-1, True, 1.2, "100.00"])
def test_invalid_prices_cannot_change_catalog(commercial, price):
    client, _, _, _ = commercial
    feature = Feature.objects.get(key="fleet_fuel")
    before = feature.monthly_price
    response = client.patch(f"/api/v1/admin/features/{feature.key}/pricing", {
        "monthly_price": price, "reason": "Invalid amount rejection",
    }, format="json")
    assert response.status_code == 400
    feature.refresh_from_db()
    assert feature.monthly_price == before


def test_pricing_is_super_admin_only_and_reason_is_required(commercial):
    client, staff, _, _ = commercial
    url = "/api/v1/admin/features/fleet_fuel/pricing"
    assert client.patch(url, {"monthly_price": 100}, format="json").status_code == 400
    staff.role = "BILLING_ADMIN"; staff.save()
    assert client.patch(url, {"monthly_price": 100, "reason": "Unauthorized price update"}, format="json").status_code == 403


def test_fleet_module_override_is_enforced_at_api(commercial):
    client, staff, tenant, plan = commercial
    from .models import TenantFeatureOverride
    fuel = Feature.objects.get(key="fleet_fuel")
    TenantFeatureOverride.objects.create(tenant=tenant, feature=fuel, enabled=False,
        reason="Fuel is not included in this company package", created_by=staff.user)
    ops = User.objects.create_user(username="catalog-fleet-ops", email="catalog-ops@example.test")
    Membership.objects.create(tenant=tenant, user=ops, role="FLEET")
    workspace_client = APIClient(); workspace_client.force_authenticate(user=ops)
    workspace_client.credentials(HTTP_X_WORKSPACE=tenant.workspace_key)
    assert workspace_client.get("/api/v1/fleet/fuel").status_code == 403
    assert workspace_client.get("/api/v1/fleet/vehicles").status_code == 200
    features = entitlements_for(tenant)["features"]
    assert features["fleet_tracking"]["enabled"] is True
    assert features["fleet_fuel"]["enabled"] is False


def test_legacy_company_master_override_keeps_access_until_module_is_configured(commercial):
    _, staff, tenant, plan = commercial
    from .models import TenantFeatureOverride
    PlanFeature.objects.filter(plan=plan, feature__key="fleet_management").update(enabled=False)
    TenantFeatureOverride.objects.create(tenant=tenant, feature=Feature.objects.get(key="fleet_management"),
        enabled=True, reason="Existing company fleet access", created_by=staff.user)
    assert entitlements_for(tenant)["features"]["fleet_fuel"]["enabled"] is True
    PlanFeature.objects.create(plan=plan, feature=Feature.objects.get(key="fleet_fuel"), enabled=False)
    assert entitlements_for(tenant)["features"]["fleet_fuel"]["enabled"] is False
