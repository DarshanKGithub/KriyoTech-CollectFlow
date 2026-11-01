from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Membership, User
from tenants.models import Tenant
from .models import FleetDriver, FleetTrip, FleetTripLocation, FleetTripLocationSample, FleetVehicle


@pytest.mark.django_db
def test_driver_location_updates_are_retained_and_playback_is_bounded():
    tenant = Tenant.objects.create(name="Tracking", workspace_key="tracking-test")
    driver_user = User.objects.create_user(username="tracking-driver", email="tracking-driver@example.test", password="test-pass")
    ops_user = User.objects.create_user(username="tracking-ops", email="tracking-ops@example.test", password="test-pass")
    Membership.objects.create(tenant=tenant, user=driver_user, role=Membership.Role.DRIVER)
    Membership.objects.create(tenant=tenant, user=ops_user, role=Membership.Role.FLEET)
    driver = FleetDriver.objects.create(tenant=tenant, name="Driver", user=driver_user)
    vehicle = FleetVehicle.objects.create(tenant=tenant, registration_number="TRACK123", normalized_registration="TRACK123")
    trip = FleetTrip.objects.create(tenant=tenant, trip_number="TRACK-1", driver=driver, vehicle=vehicle,
        status=FleetTrip.Status.IN_PROGRESS, created_by=ops_user)
    client = APIClient()
    client.force_authenticate(user=driver_user)
    client.credentials(HTTP_X_WORKSPACE=tenant.workspace_key)
    captured = timezone.now() - timedelta(seconds=20)

    first_event_id = uuid4()

    def report(second, latitude, event_id=None):
        return client.post(f"/api/v1/fleet/trips/{trip.id}/location", {
            "latitude": latitude, "longitude": "72.900000", "captured_at": (captured + timedelta(seconds=second)).isoformat(),
            "client_event_id": str(event_id or uuid4()), "accuracy_m": "8", "speed_mps": "5",
        }, format="json")

    assert report(0, "19.100000", first_event_id).status_code == 201
    assert report(10, "19.200000").status_code == 201
    late = report(5, "19.150000")
    assert late.status_code == 200 and late.data["historical_sample_recorded"] is True
    duplicate = report(0, "19.100000", first_event_id)
    assert duplicate.status_code == 200 and duplicate.data["duplicate"] is True
    assert FleetTripLocationSample.objects.filter(tenant=tenant, trip=trip).count() == 3
    latest = FleetTripLocation.objects.get(tenant=tenant, trip=trip)
    assert str(latest.latitude) == "19.200000"

    client.force_authenticate(user=ops_user)
    history = client.get(f"/api/v1/fleet/trips/{trip.id}/location-history?limit=1")
    assert history.status_code == 200
    assert history.data["count"] == 1 and history.data["has_more"] is True
    assert history.data["next_offset"] == 1
    second_page = client.get(f"/api/v1/fleet/trips/{trip.id}/location-history?limit=1&offset=1")
    assert second_page.data["count"] == 1 and second_page.data["has_more"] is True
    assert second_page.data["points"][0]["latitude"] == "19.150000"
    third_page = client.get(f"/api/v1/fleet/trips/{trip.id}/location-history?limit=1&offset=2")
    assert third_page.data["points"][0]["latitude"] == "19.200000"


@pytest.mark.django_db
def test_location_history_is_tenant_and_driver_scoped():
    tenant = Tenant.objects.create(name="Tracking scope", workspace_key="tracking-scope")
    other_tenant = Tenant.objects.create(name="Other tracking", workspace_key="other-tracking")
    driver_user = User.objects.create_user(username="scoped-driver", email="scoped-driver@example.test", password="test-pass")
    Membership.objects.create(tenant=tenant, user=driver_user, role=Membership.Role.DRIVER)
    vehicle = FleetVehicle.objects.create(tenant=tenant, registration_number="SCOPE123", normalized_registration="SCOPE123")
    other_vehicle = FleetVehicle.objects.create(tenant=other_tenant, registration_number="OTHER123", normalized_registration="OTHER123")
    driver = FleetDriver.objects.create(tenant=tenant, name="Driver", user=driver_user)
    other_driver = FleetDriver.objects.create(tenant=tenant, name="Different driver")
    foreign_driver = FleetDriver.objects.create(tenant=other_tenant, name="Foreign driver")
    assigned = FleetTrip.objects.create(tenant=tenant, trip_number="ASSIGNED", driver=driver, vehicle=vehicle)
    unassigned = FleetTrip.objects.create(tenant=tenant, trip_number="UNASSIGNED", driver=other_driver, vehicle=vehicle)
    foreign = FleetTrip.objects.create(tenant=other_tenant, trip_number="FOREIGN", driver=foreign_driver, vehicle=other_vehicle)
    client = APIClient()
    client.force_authenticate(user=driver_user)
    client.credentials(HTTP_X_WORKSPACE=tenant.workspace_key)
    root = "/api/v1/fleet/trips/{}"
    assert client.get(root.format(assigned.id) + "/location-history").status_code == 200
    assert client.get(root.format(unassigned.id) + "/location-history").status_code == 404
    assert client.get(root.format(foreign.id) + "/location-history", HTTP_X_WORKSPACE=other_tenant.workspace_key).status_code == 404
    assert client.get(root.format(assigned.id) + "/location-history?limit=5001").status_code == 400
