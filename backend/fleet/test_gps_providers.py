import hashlib
import hmac
import json
import time
from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Membership, User
from tenants.models import Tenant
from .models import FleetDriver, FleetGpsDevice, FleetStopEpisode, FleetTrip, FleetTripLocation, FleetTripLocationSample, FleetVehicle
from .tasks import prune_fleet_location_history


@pytest.fixture
def gps_provider_workspace(db):
    tenant = Tenant.objects.create(name="GPS provider test", workspace_key="gps-provider-test")
    driver_user = User.objects.create_user(username="gps-driver", email="gps-driver@example.test", password="test-pass")
    fleet_user = User.objects.create_user(username="gps-ops", email="gps-ops@example.test", password="test-pass")
    Membership.objects.create(tenant=tenant, user=driver_user, role=Membership.Role.DRIVER)
    Membership.objects.create(tenant=tenant, user=fleet_user, role=Membership.Role.FLEET)
    driver = FleetDriver.objects.create(tenant=tenant, name="GPS Driver", user=driver_user)
    vehicle = FleetVehicle.objects.create(tenant=tenant, registration_number="GPS123", normalized_registration="GPS123")
    trip = FleetTrip.objects.create(tenant=tenant, trip_number="GPS-1", driver=driver, vehicle=vehicle,
        status=FleetTrip.Status.IN_PROGRESS, created_by=fleet_user)
    device = FleetGpsDevice.objects.create(tenant=tenant, provider="ACME_TRACKER", device_id="truck-901",
        vehicle=vehicle, created_by=fleet_user)
    return tenant, trip, device, fleet_user


def signed_provider_post(payload, secret, timestamp=None, signature_override=None):
    timestamp = timestamp or str(int(time.time()))
    body = json.dumps(payload, separators=(",", ":")).encode()
    signature = hmac.new(secret, timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    client = APIClient()
    return client.post("/api/v1/fleet/gps-provider/events", body, content_type="application/json",
        HTTP_X_FLEET_TIMESTAMP=timestamp,
        HTTP_X_FLEET_SIGNATURE=signature_override or signature)


def provider_event(event_id, captured_at=None, **overrides):
    return {"provider": "ACME_TRACKER", "device_id": "truck-901", "event_id": event_id,
        "captured_at": (captured_at or timezone.now() - timedelta(seconds=20)).isoformat(),
        "latitude": 19.076, "longitude": 72.8777, "accuracy_m": 12, "speed_kmh": 42.5,
        "heading_degrees": 87, **overrides}


@pytest.mark.django_db
def test_signed_provider_event_is_idempotent_and_updates_latest_location(gps_provider_workspace, monkeypatch):
    tenant, trip, _device, _fleet_user = gps_provider_workspace
    secret = b"test-provider-secret-that-is-at-least-32-bytes"
    monkeypatch.setenv("FLEET_GPS_WEBHOOK_SECRET", secret.decode())
    payload = provider_event("vendor-evt-1")

    accepted = signed_provider_post(payload, secret)
    replay = signed_provider_post(payload, secret)

    assert accepted.status_code == 201, accepted.data
    assert accepted.data["trip_id"] == str(trip.id)
    assert accepted.data["source_provider"] == "ACME_TRACKER"
    assert replay.status_code == 200 and replay.data["duplicate"] is True
    assert FleetTripLocationSample.objects.filter(tenant=tenant, trip=trip).count() == 1
    latest = FleetTripLocation.objects.get(tenant=tenant, trip=trip)
    assert latest.source_provider == "ACME_TRACKER"
    assert str(latest.latitude) == "19.076000"


@pytest.mark.django_db
def test_late_provider_sample_is_kept_without_regressing_latest(gps_provider_workspace, monkeypatch):
    tenant, trip, _device, _fleet_user = gps_provider_workspace
    secret = b"test-provider-secret-that-is-at-least-32-bytes"
    monkeypatch.setenv("FLEET_GPS_WEBHOOK_SECRET", secret.decode())
    now = timezone.now()
    latest_payload = provider_event("vendor-evt-new", now - timedelta(seconds=10), latitude=19.2)
    late_payload = provider_event("vendor-evt-late", now - timedelta(seconds=30), latitude=19.1)

    assert signed_provider_post(latest_payload, secret).status_code == 201
    late = signed_provider_post(late_payload, secret)

    assert late.status_code == 200 and late.data["historical_sample_recorded"] is True
    assert FleetTripLocationSample.objects.filter(tenant=tenant, trip=trip).count() == 2
    assert str(FleetTripLocation.objects.get(tenant=tenant, trip=trip).latitude) == "19.200000"


@pytest.mark.django_db
def test_provider_signature_and_assignment_fail_closed(gps_provider_workspace, monkeypatch):
    tenant, trip, device, _fleet_user = gps_provider_workspace
    secret = b"test-provider-secret-that-is-at-least-32-bytes"
    monkeypatch.setenv("FLEET_GPS_WEBHOOK_SECRET", secret.decode())
    payload = provider_event("vendor-evt-bad-signature")
    invalid = signed_provider_post(payload, secret, signature_override="0" * 64)
    assert invalid.status_code == 401
    assert not FleetTripLocationSample.objects.filter(tenant=tenant, trip=trip).exists()

    device.active = False
    device.save(update_fields=["active"])
    inactive = signed_provider_post(provider_event("vendor-evt-inactive"), secret)
    assert inactive.status_code == 404
    assert not FleetTripLocationSample.objects.filter(tenant=tenant, trip=trip).exists()


@pytest.mark.django_db
def test_location_retention_deletes_expired_rows_in_bounded_batches(gps_provider_workspace, monkeypatch):
    tenant, trip, _device, _fleet_user = gps_provider_workspace
    monkeypatch.setenv("FLEET_GPS_HISTORY_RETENTION_DAYS", "30")
    old = timezone.now() - timedelta(days=31)
    recent = timezone.now() - timedelta(days=1)
    old_sample = FleetTripLocationSample.objects.create(tenant=tenant, trip=trip, latitude=19, longitude=72,
        captured_at=old, client_event_id=uuid4())
    recent_sample = FleetTripLocationSample.objects.create(tenant=tenant, trip=trip, latitude=19, longitude=72,
        captured_at=recent, client_event_id=uuid4())
    FleetTripLocation.objects.create(tenant=tenant, trip=trip, latitude=19, longitude=72,
        captured_at=old, client_event_id=uuid4())

    result = prune_fleet_location_history(batch_size=1)

    assert result["samples_deleted"] == 1
    assert result["latest_locations_deleted"] == 1
    assert result["more_pending"] is False
    assert not FleetTripLocationSample.objects.filter(id=old_sample.id).exists()
    assert FleetTripLocationSample.objects.filter(id=recent_sample.id).exists()
    assert not FleetTripLocation.objects.filter(trip=trip).exists()


@pytest.mark.django_db
def test_engine_idle_requires_consecutive_ignition_on_and_low_speed_tracker_samples(gps_provider_workspace, monkeypatch):
    tenant, trip, _device, fleet_user = gps_provider_workspace
    secret = b"test-provider-secret-that-is-at-least-32-bytes"
    monkeypatch.setenv("FLEET_GPS_WEBHOOK_SECRET", secret.decode())
    started = timezone.now() - timedelta(seconds=60)
    first = signed_provider_post(provider_event("idle-1", started, speed_kmh=0, ignition_on=True), secret)
    second = signed_provider_post(provider_event("idle-2", started + timedelta(seconds=30), speed_kmh=0, ignition_on=True), secret)
    engine_off = signed_provider_post(provider_event("idle-3", started + timedelta(seconds=60), speed_kmh=0, ignition_on=False), secret)

    assert first.status_code == 201 and second.status_code == 201 and engine_off.status_code == 201
    episode = FleetStopEpisode.objects.get(tenant=tenant, trip=trip, ended_at__isnull=True)
    assert episode.engine_idle_seconds == 30
    assert episode.last_ignition_on is False
    client = APIClient()
    client.force_authenticate(user=fleet_user)
    client.credentials(HTTP_X_WORKSPACE=tenant.workspace_key)
    live = client.get("/api/v1/fleet/live-locations")
    assert live.status_code == 200
    stop_data = live.data["trips"][0]["stationary_stop"]
    assert stop_data["engine_idle_seconds"] == 30 and stop_data["ignition_on"] is False


@pytest.mark.django_db
def test_tracker_ignition_value_must_be_json_boolean(gps_provider_workspace, monkeypatch):
    _tenant, _trip, _device, _fleet_user = gps_provider_workspace
    secret = b"test-provider-secret-that-is-at-least-32-bytes"
    monkeypatch.setenv("FLEET_GPS_WEBHOOK_SECRET", secret.decode())

    response = signed_provider_post(provider_event("idle-invalid", ignition_on="true"), secret)

    assert response.status_code == 400
