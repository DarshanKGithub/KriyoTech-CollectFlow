from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from tenants.models import Tenant
from .configuration import config_service
from .models import AdminAuditLog, AdminStaff, Feature, Plan, PlanFeature, Subscription, TenantFeatureOverride
from .services import entitlements_for
from .test_helpers import authenticate_staff


@pytest.fixture
def env(db):
    cache.clear()
    user = User.objects.create_user(username="config-admin", email="config@example.test")
    staff = AdminStaff.objects.create(user=user, role="SUPER_ADMIN")
    tenant = Tenant.objects.create(name="Configuration Test", workspace_key="config-test")
    plan = Plan.objects.create(name="Config Plan", slug="config-plan")
    feature, _ = Feature.objects.get_or_create(key="fleet_management", defaults={"name": "Fleet"})
    PlanFeature.objects.create(plan=plan, feature=feature, enabled=True)
    Subscription.objects.create(tenant=tenant, plan=plan, status="ACTIVE")
    client = APIClient()
    authenticate_staff(client, staff)
    return client, user, tenant, feature


def payload(**kwargs):
    return {"feature_key": "fleet_management", "enabled": False, "reason": "Temporary fleet access change", **kwargs}


def test_single_override_supports_uuid_tenant_preserves_history_actor_and_cache(env):
    client, user, tenant, feature = env
    url = f"/api/v1/admin/configuration/tenant/{tenant.pk}/feature"
    assert client.get(f"/api/v1/admin/configuration/tenant/{tenant.pk}").data["features"][feature.key]["enabled"]
    first = client.post(url, payload(created_by="untrusted-input"), format="json")
    assert first.status_code == 201, first.data
    assert not client.get(f"/api/v1/admin/configuration/tenant/{tenant.pk}").data["features"][feature.key]["enabled"]
    second = client.post(url, payload(enabled=True, limit_value=0), format="json")
    assert second.status_code == 201, second.data
    rows = TenantFeatureOverride.objects.filter(tenant=tenant, feature=feature)
    assert rows.count() == 2 and all(row.created_by_id == user.pk for row in rows)
    assert rows.get(pk=first.data["override_id"]).enabled is False
    assert entitlements_for(tenant)["features"][feature.key]["enabled"] is True
    assert AdminAuditLog.objects.filter(tenant=tenant, actor=user, action="TENANT_FEATURE_OVERRIDE_CHANGED").count() == 2


@pytest.mark.parametrize("kind", ["create", "bulk"])
def test_create_and_bulk_routes_apply_overrides_with_server_actor(env, kind):
    client, user, tenant, feature = env
    if kind == "create":
        result = client.post("/api/v1/admin/configuration/features", {"tenant_id": str(tenant.pk), "feature_overrides": [payload(created_by="forged")]}, format="json")
        assert result.status_code == 201, result.data
    else:
        result = client.patch(f"/api/v1/admin/configuration/tenant/{tenant.pk}", {"updates": [payload(created_by="forged")]}, format="json")
        assert result.status_code == 200, result.data
    assert TenantFeatureOverride.objects.get(tenant=tenant).created_by_id == user.pk
    assert not entitlements_for(tenant)["features"][feature.key]["enabled"]


@pytest.mark.parametrize("change", [
    {"enabled": "false"}, {"enabled": 1}, {"limit_value": -1}, {"limit_value": True},
    {"limit_value": "2"}, {"reason": []}, {"reason": "short"},
    {"expires_at": "invalid"}, {"expires_at": "2027-01-01T12:00:00"},
    {"expires_at": "2000-01-01T12:00:00Z"}, {"feature_key": []},
])
def test_invalid_single_override_does_not_change_data(env, change):
    client, _, tenant, _ = env
    response = client.post(f"/api/v1/admin/configuration/tenant/{tenant.pk}/feature", payload(**change), format="json")
    assert response.status_code == 400, response.data
    assert not TenantFeatureOverride.objects.exists()


def test_expiring_override_deleted_company_and_read_only_access(env):
    client, user, tenant, feature = env
    future = (timezone.now() + timedelta(days=1)).isoformat()
    response = client.post(f"/api/v1/admin/configuration/tenant/{tenant.pk}/feature", payload(expires_at=future), format="json")
    assert response.status_code == 201, response.data
    tenant.is_deleted = True
    tenant.save()
    assert client.post(f"/api/v1/admin/configuration/tenant/{tenant.pk}/feature", payload(), format="json").status_code == 400
    AdminStaff.objects.filter(user=user).update(role="READ_ONLY")
    assert client.post(f"/api/v1/admin/configuration/tenant/{tenant.pk}/feature", payload(), format="json").status_code == 403


def test_malformed_bulk_and_partial_failures_are_explicit(env):
    client, _, tenant, _ = env
    url = f"/api/v1/admin/configuration/tenant/{tenant.pk}"
    for data in ([payload()], {"updates": "bad"}, {"updates": ["bad"]}):
        assert client.patch(url, data, format="json").status_code == 400
    response = client.patch(url, {"updates": [payload(), payload(feature_key="missing")]}, format="json")
    assert response.status_code == 207, response.data
    assert len(response.data["results"]) == len(response.data["errors"]) == 1


def test_global_configuration_cache_clear_does_not_clear_login_throttles(env):
    client, _, tenant, feature = env
    config_service.get_feature_configuration(tenant)
    cache.set("unrelated-throttle-test", "keep")
    PlanFeature.objects.filter(feature=feature).update(enabled=False)
    response = client.post("/api/v1/admin/configuration/cache/clear", {}, format="json")
    assert response.status_code == 200, response.data
    assert cache.get("unrelated-throttle-test") == "keep"
    assert not config_service.get_feature_configuration(tenant)["features"][feature.key]["enabled"]
