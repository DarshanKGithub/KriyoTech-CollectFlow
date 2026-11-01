from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Membership, User
from audit.models import AuditLog
from tenants.models import Tenant
from .models import FleetDriver, FleetGeofence, FleetGeofenceDwellEpisode, FleetGeofenceEvent, FleetGeofenceVersion, FleetStopEpisode, FleetTrip, FleetVehicle


@pytest.fixture
def tracking_workspace(db):
    tenant = Tenant.objects.create(name="Geofence test", workspace_key="geofence-test")
    driver_user = User.objects.create_user(username="geo-driver", email="geo-driver@example.test", password="test-pass")
    fleet_user = User.objects.create_user(username="geo-ops", email="geo-ops@example.test", password="test-pass")
    customer_user = User.objects.create_user(username="geo-customer", email="geo-customer@example.test", password="test-pass")
    Membership.objects.create(tenant=tenant, user=driver_user, role=Membership.Role.DRIVER)
    Membership.objects.create(tenant=tenant, user=fleet_user, role=Membership.Role.FLEET)
    Membership.objects.create(tenant=tenant, user=customer_user, role=Membership.Role.PURCHASE)
    driver = FleetDriver.objects.create(tenant=tenant, name="Driver", user=driver_user)
    vehicle = FleetVehicle.objects.create(tenant=tenant, registration_number="GEO123", normalized_registration="GEO123")
    trip = FleetTrip.objects.create(tenant=tenant, trip_number="GEO-1", driver=driver, vehicle=vehicle,
        status=FleetTrip.Status.IN_PROGRESS, created_by=fleet_user)
    fleet_client = APIClient()
    fleet_client.force_authenticate(user=fleet_user)
    fleet_client.credentials(HTTP_X_WORKSPACE=tenant.workspace_key)
    driver_client = APIClient()
    driver_client.force_authenticate(user=driver_user)
    driver_client.credentials(HTTP_X_WORKSPACE=tenant.workspace_key)
    return tenant, trip, fleet_user, driver_client, fleet_client


def circle_payload(name="Main depot"):
    return {"name": name, "site_type": "WAREHOUSE", "shape": "CIRCLE",
        "geometry": {"center": [72.9, 19.1], "radius_m": 500}, "reason": "Initial site boundary setup"}


def report(client, trip, captured_at, latitude, longitude, accuracy="5"):
    return client.post(f"/api/v1/fleet/trips/{trip.id}/location", {
        "latitude": str(latitude), "longitude": str(longitude), "accuracy_m": accuracy,
        "captured_at": captured_at.isoformat(), "client_event_id": str(uuid4()),
    }, format="json")


@pytest.mark.django_db
def test_geofence_crud_keeps_immutable_versions_and_rejects_stale_edit(tracking_workspace):
    tenant, trip, fleet_user, driver_client, fleet_client = tracking_workspace
    created = fleet_client.post("/api/v1/fleet/geofences", circle_payload(), format="json")
    assert created.status_code == 201, created.data
    fence_id = created.data["id"]
    assert created.data["current_version"] == 1
    updated = fleet_client.patch(f"/api/v1/fleet/geofences/{fence_id}", {
        "expected_version": 1, "shape": "CIRCLE", "geometry": {"center": [72.901, 19.1], "radius_m": 600},
        "reason": "Move the site entrance boundary",
    }, format="json")
    assert updated.status_code == 200 and updated.data["current_version"] == 2
    assert FleetGeofenceVersion.objects.filter(geofence_id=fence_id).count() == 2
    original_version = FleetGeofenceVersion.objects.get(geofence_id=fence_id, version=1)
    original_version.reason = "Overwrite history"
    with pytest.raises(ValueError, match="immutable"):
        original_version.save()
    stale = fleet_client.patch(f"/api/v1/fleet/geofences/{fence_id}", {
        "expected_version": 1, "active": False,
    }, format="json")
    assert stale.status_code == 409
    assert fleet_client.get("/api/v1/fleet/geofences").data["geofences"][0]["current_version"] == 2
    assert AuditLog.objects.filter(tenant=tenant, action__startswith="FLEET_GEOFENCE_").count() == 2


@pytest.mark.django_db
def test_geofence_transition_requires_stable_accurate_fixes_and_records_arrival_departure(tracking_workspace):
    tenant, trip, fleet_user, driver_client, fleet_client = tracking_workspace
    created = fleet_client.post("/api/v1/fleet/geofences", circle_payload(), format="json")
    assert created.status_code == 201, created.data
    start = timezone.now() - timedelta(minutes=3)

    assert report(driver_client, trip, start, 19.1, 72.9).status_code == 201
    assert not FleetGeofenceEvent.objects.filter(tenant=tenant).exists()
    assert report(driver_client, trip, start + timedelta(seconds=31), 19.1, 72.9).status_code == 201
    arrival = FleetGeofenceEvent.objects.get(tenant=tenant)
    assert arrival.event_type == FleetGeofenceEvent.EventType.ARRIVAL

    assert report(driver_client, trip, start + timedelta(seconds=62), 19.12, 72.9, accuracy="250").status_code == 201
    assert FleetGeofenceEvent.objects.filter(tenant=tenant).count() == 1
    assert report(driver_client, trip, start + timedelta(seconds=63), 19.12, 72.9).status_code == 201
    assert FleetGeofenceEvent.objects.filter(tenant=tenant).count() == 1
    assert report(driver_client, trip, start + timedelta(seconds=94), 19.12, 72.9).status_code == 201
    events = list(FleetGeofenceEvent.objects.filter(tenant=tenant).order_by("occurred_at"))
    assert [event.event_type for event in events] == [FleetGeofenceEvent.EventType.ARRIVAL, FleetGeofenceEvent.EventType.DEPARTURE]
    api_events = fleet_client.get("/api/v1/fleet/geofence-events?limit=1")
    assert api_events.status_code == 200 and api_events.data["has_more"] is True


@pytest.mark.django_db
def test_geofence_shapes_and_management_roles_are_validated_and_tenant_scoped(tracking_workspace):
    tenant, trip, fleet_user, driver_client, fleet_client = tracking_workspace
    invalid = {"name": "Bad polygon", "site_type": "FACTORY", "shape": "POLYGON",
        "geometry": {"type": "Polygon", "coordinates": [[[72.9, 19.1], [72.9, 19.1], [72.9, 19.1]]]},
        "reason": "Attempt invalid polygon"}
    assert fleet_client.post("/api/v1/fleet/geofences", invalid, format="json").status_code == 400
    forbidden = APIClient()
    forbidden.force_authenticate(user=User.objects.get(email="geo-customer@example.test"))
    forbidden.credentials(HTTP_X_WORKSPACE=tenant.workspace_key)
    assert forbidden.post("/api/v1/fleet/geofences", circle_payload(), format="json").status_code == 403
    created = fleet_client.post("/api/v1/fleet/geofences", circle_payload(), format="json")
    other_tenant = Tenant.objects.create(name="Other", workspace_key="other-geofence")
    other_user = User.objects.create_user(username="other-ops", email="other-ops@example.test", password="test-pass")
    Membership.objects.create(tenant=other_tenant, user=other_user, role=Membership.Role.FLEET)
    other_client = APIClient()
    other_client.force_authenticate(user=other_user)
    other_client.credentials(HTTP_X_WORKSPACE=other_tenant.workspace_key)
    assert other_client.patch(f"/api/v1/fleet/geofences/{created.data['id']}", {"expected_version": 1, "active": False}, format="json").status_code == 404
    assert fleet_client.get("/api/v1/fleet/geofence-events?trip_id=not-a-uuid").status_code == 400


@pytest.mark.django_db
def test_long_site_dwell_creates_review_case_and_departure_closes_episode(tracking_workspace):
    tenant, trip, fleet_user, driver_client, fleet_client = tracking_workspace
    payload = circle_payload("Loading bay")
    payload["dwell_alert_minutes"] = 1
    created = fleet_client.post("/api/v1/fleet/geofences", payload, format="json")
    assert created.status_code == 201, created.data
    start = timezone.now() - timedelta(minutes=4)
    for seconds in (0, 31, 62, 93):
        response = report(driver_client, trip, start + timedelta(seconds=seconds), 19.1, 72.9)
        assert response.status_code == 201, response.data
    episode = FleetGeofenceDwellEpisode.objects.get(tenant=tenant, trip=trip)
    assert episode.ended_at is None and episode.sample_count == 3
    case = episode.exception_case
    assert case.category == "LONG_SITE_DWELL"
    assert case.evidence["geofence_name"] == "Loading bay"
    for seconds in (124, 155):
        assert report(driver_client, trip, start + timedelta(seconds=seconds), 19.12, 72.9).status_code == 201
    episode.refresh_from_db()
    assert episode.ended_at is not None and episode.end_reason == "DEPARTURE"


@pytest.mark.django_db
def test_stale_gps_closes_open_stop_and_dwell_episodes(tracking_workspace):
    from .tracking_episodes import expire_stale_tracking_episodes

    tenant, trip, fleet_user, driver_client, fleet_client = tracking_workspace
    started = timezone.now() - timedelta(minutes=8)
    fence = FleetGeofence.objects.create(tenant=tenant, name="Stale-test site", created_by=fleet_user)
    stop = FleetStopEpisode.objects.create(tenant=tenant, trip=trip, started_at=started,
        last_sample_at=started, start_latitude=19.1, start_longitude=72.9,
        last_latitude=19.1, last_longitude=72.9)
    dwell = FleetGeofenceDwellEpisode.objects.create(tenant=tenant, trip=trip, geofence=fence,
        version=1, started_at=started, last_sample_at=started, last_latitude=19.1, last_longitude=72.9)
    result = expire_stale_tracking_episodes(now=timezone.now())
    stop.refresh_from_db(); dwell.refresh_from_db()
    assert result == {"stationary_closed": 1, "dwell_closed": 1, "route_deviations_closed": 0}
    assert stop.status == FleetStopEpisode.Status.INTERRUPTED and stop.ended_at == started
    assert dwell.end_reason == FleetGeofenceDwellEpisode.EndReason.GPS_GAP and dwell.ended_at == started
