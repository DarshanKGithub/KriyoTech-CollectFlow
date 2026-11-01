from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone

from accounts.models import User
from tenants.models import Tenant
from .models import (FleetDriver, FleetExceptionCase, FleetGeofence, FleetGeofenceVersion,
    FleetRouteDeviationEpisode, FleetRouteSnapshot, FleetTrip, FleetTripLocationSample, FleetVehicle)
from .routing import record_route_deviation, store_route_snapshot


@pytest.fixture
def route_context(db):
    tenant = Tenant.objects.create(name="Route review", workspace_key="route-review")
    user = User.objects.create_user(username="route-driver", email="route-driver@example.test", password="test-pass")
    driver = FleetDriver.objects.create(tenant=tenant, name="Driver", user=user)
    vehicle = FleetVehicle.objects.create(tenant=tenant, registration_number="ROUTE123", normalized_registration="ROUTE123")
    trip = FleetTrip.objects.create(tenant=tenant, trip_number="ROUTE-1", driver=driver, vehicle=vehicle,
        status=FleetTrip.Status.IN_PROGRESS)
    snapshot = FleetRouteSnapshot.objects.create(tenant=tenant, trip=trip, version=1,
        route_fingerprint="a"*64, route_path=[[0.0, 0.0], [0.0, 1.0]], distance_m=111000,
        duration_seconds=3600, destination="Test destination")
    return tenant, user, trip, snapshot


def make_sample(tenant, user, trip, when, latitude, longitude, accuracy="5"):
    return FleetTripLocationSample.objects.create(tenant=tenant, trip=trip, reported_by=user,
        latitude=latitude, longitude=longitude, accuracy_m=accuracy, captured_at=when,
        client_event_id=uuid4())


@pytest.mark.django_db
def test_route_deviation_needs_two_accurate_fixes_and_closes_after_rejoining(route_context):
    tenant, user, trip, snapshot = route_context
    start = timezone.now() - timedelta(minutes=2)
    first = make_sample(tenant, user, trip, start, "0.030000", "0.500000")
    candidate = record_route_deviation(first)
    assert candidate.status == FleetRouteDeviationEpisode.Status.CANDIDATE
    assert not FleetExceptionCase.objects.filter(tenant=tenant, category="ROUTE_DEVIATION").exists()

    confirming = make_sample(tenant, user, trip, start + timedelta(seconds=31), "0.031000", "0.500000")
    active = record_route_deviation(confirming)
    assert active.status == FleetRouteDeviationEpisode.Status.ACTIVE
    case = active.exception_case
    assert case.category == "ROUTE_DEVIATION"
    assert case.evidence["route_version"] == snapshot.version
    assert case.evidence["sample_count"] == 2

    rejoined = make_sample(tenant, user, trip, start + timedelta(seconds=62), "0.001000", "0.500000")
    closed = record_route_deviation(rejoined)
    assert closed.status == FleetRouteDeviationEpisode.Status.CLOSED
    assert closed.end_reason == FleetRouteDeviationEpisode.EndReason.REJOINED
    assert FleetExceptionCase.objects.filter(tenant=tenant, category="ROUTE_DEVIATION").count() == 1


@pytest.mark.django_db
def test_planned_geofence_exempts_a_route_deviation_and_inaccurate_samples_are_ignored(route_context):
    tenant, user, trip, _ = route_context
    fence = FleetGeofence.objects.create(tenant=tenant, name="Planned customer stop")
    FleetGeofenceVersion.objects.create(geofence=fence, version=1, shape=FleetGeofence.Shape.CIRCLE,
        geometry={"center": [0.5, 0.03], "radius_m": 500})
    when = timezone.now() - timedelta(minutes=1)
    poor_fix = make_sample(tenant, user, trip, when, "0.030000", "0.500000", accuracy="250")
    assert record_route_deviation(poor_fix) is None
    planned_stop = make_sample(tenant, user, trip, when + timedelta(seconds=31), "0.030000", "0.500000")
    assert record_route_deviation(planned_stop) is None
    assert not FleetRouteDeviationEpisode.objects.filter(tenant=tenant).exists()


@pytest.mark.django_db
def test_new_route_snapshot_supersedes_unconfirmed_old_route_deviation(route_context):
    tenant, user, trip, _ = route_context
    sample = make_sample(tenant, user, trip, timezone.now() - timedelta(minutes=1), "0.030000", "0.500000")
    episode = record_route_deviation(sample)
    updated = store_route_snapshot(trip=trip, encoded_polyline="???_ibE", distance_m=111000,
        duration_seconds=1800, destination="Test destination B")
    episode.refresh_from_db()
    assert updated.version == 2
    assert episode.status == FleetRouteDeviationEpisode.Status.SUPERSEDED
    assert episode.end_reason == FleetRouteDeviationEpisode.EndReason.ROUTE_UPDATED


@pytest.mark.django_db
def test_gps_gap_interrupts_route_deviation_episode(route_context):
    from .tracking_episodes import expire_stale_tracking_episodes

    tenant, user, trip, _ = route_context
    last_sample_at = timezone.now() - timedelta(minutes=8)
    sample = make_sample(tenant, user, trip, last_sample_at, "0.030000", "0.500000")
    episode = record_route_deviation(sample)
    result = expire_stale_tracking_episodes(now=timezone.now())
    episode.refresh_from_db()
    assert result["route_deviations_closed"] == 1
    assert episode.status == FleetRouteDeviationEpisode.Status.INTERRUPTED
    assert episode.end_reason == FleetRouteDeviationEpisode.EndReason.GPS_GAP
