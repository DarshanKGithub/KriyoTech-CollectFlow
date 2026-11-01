import json
import os
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from urllib.error import URLError
from uuid import uuid4

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Membership, User
from tenants.models import Tenant
from .models import (FleetCustomer, FleetDriver, FleetDriverSchedule, FleetResourceReservation,
    FleetDispatchPlan, FleetDispatchRouteAttempt, FleetRouteSnapshot, FleetTrip, FleetTripManifestItem, FleetTripStop,
    FleetVehicle, TransportOrder)


@pytest.fixture
def dispatch_workspace(db):
    tenant = Tenant.objects.create(name="Dispatch planning", workspace_key="dispatch-planning-test")
    user = User.objects.create_user(username="dispatch-operator", email="dispatch@example.test", password="test-pass")
    Membership.objects.create(tenant=tenant, user=user, role="OWNER")
    client = APIClient(); client.force_authenticate(user=user)
    client.credentials(HTTP_X_WORKSPACE=tenant.workspace_key)
    customer = FleetCustomer.objects.create(tenant=tenant, name="Planning customer")
    truck = FleetVehicle.objects.create(tenant=tenant, registration_number="PLAN-001", normalized_registration="PLAN-001",
        vehicle_type="RIGID", capacity=10, capacity_unit="TONNE")
    driver = FleetDriver.objects.create(tenant=tenant, name="Planning driver")
    now = timezone.now() + timedelta(hours=1)
    orders = [TransportOrder.objects.create(tenant=tenant, customer=customer, order_number=f"PLAN-{n}",
        origin=f"Pickup {n}", destination=f"Drop {n}", origin_latitude=Decimal("19.076000"),
        origin_longitude=Decimal("72.877700"), destination_latitude=Decimal("18.520400"),
        destination_longitude=Decimal("73.856700"), load_quantity=Decimal("2"), load_unit="TONNE",
        pickup_due_at=now + timedelta(hours=3), delivery_due_at=now + timedelta(hours=8)) for n in (1, 2)]
    starts_at = now.isoformat()
    ends_at = (now + timedelta(hours=8)).isoformat()
    return tenant, user, client, customer, truck, driver, orders, starts_at, ends_at


def _plan(client, orders, starts_at, ends_at):
    return client.post("/api/v1/fleet/dispatch-plans/optimize", {
        "allocations": [{"order_id": str(order.id), "quantity": "2"} for order in orders],
        "starts_at": starts_at, "ends_at": ends_at, "request_key": str(uuid4()),
    }, format="json")


@pytest.mark.django_db
def test_dispatch_plan_confirms_multi_stop_manifest_and_is_idempotent(dispatch_workspace):
    tenant, _, client, _, _, _, orders, starts_at, ends_at = dispatch_workspace
    plan = _plan(client, orders, starts_at, ends_at)
    assert plan.status_code == 201, plan.data
    option = plan.data["options"][0]
    assert len(option["route"]["stops"]) == 4
    assert [stop["kind"] for stop in option["route"]["stops"]].count("PICKUP") == 2
    body = {"option_id": option["option_id"], "fingerprint": plan.data["fingerprint"], "trip_number": "PLAN-TRIP-1"}
    confirmed = client.post(f"/api/v1/fleet/dispatch-plans/{plan.data['plan_id']}/confirm", body, format="json")
    assert confirmed.status_code == 201, confirmed.data
    trip_id = confirmed.data["trip"]["id"]
    assert FleetTripManifestItem.objects.filter(tenant=tenant, trip_id=trip_id).count() == 2
    assert FleetTripStop.objects.filter(tenant=tenant, trip_id=trip_id).count() == 4
    assert FleetResourceReservation.objects.filter(tenant=tenant, trip_id=trip_id, released_at__isnull=True).exists()
    replay = client.post(f"/api/v1/fleet/dispatch-plans/{plan.data['plan_id']}/confirm", body, format="json")
    assert replay.status_code == 200 and replay.data["idempotent_replay"] is True
    trip = FleetTrip.objects.get(tenant=tenant, id=trip_id)
    trip.starts_at = timezone.now() - timedelta(minutes=5)
    trip.save(update_fields=["starts_at"])
    assert client.post(f"/api/v1/fleet/trips/{trip_id}/start", {}, format="json").status_code == 200
    for stop in confirmed.data["trip"]["stops"]:
        arrived = client.post(f"/api/v1/fleet/trips/{trip_id}/stops/{stop['id']}/arrive", {}, format="json")
        assert arrived.status_code == 200, arrived.data
        completed = client.post(f"/api/v1/fleet/trips/{trip_id}/stops/{stop['id']}/complete", {}, format="json")
        assert completed.status_code == 200, completed.data
    finished = client.post(f"/api/v1/fleet/trips/{trip_id}/complete", {"delivery_signature_name": "Receiver"}, format="json")
    assert finished.status_code == 200, finished.data
    assert all(order.status == TransportOrder.Status.DELIVERED for order in TransportOrder.objects.filter(tenant=tenant))
    assert not FleetResourceReservation.objects.filter(tenant=tenant, trip_id=trip_id, released_at__isnull=True).exists()


@pytest.mark.django_db
def test_dispatch_plan_rejects_driver_leave_and_stale_order(dispatch_workspace):
    tenant, _, client, _, _, driver, orders, starts_at, ends_at = dispatch_workspace
    start = timezone.datetime.fromisoformat(starts_at)
    finish = timezone.datetime.fromisoformat(ends_at)
    FleetDriverSchedule.objects.create(tenant=tenant, driver=driver, kind="LEAVE", starts_at=start, ends_at=finish)
    blocked = _plan(client, orders, starts_at, ends_at)
    assert blocked.status_code == 200 and blocked.data["options"] == []
    FleetDriverSchedule.objects.all().delete()
    plan = _plan(client, orders, starts_at, ends_at)
    assert plan.status_code == 201, plan.data
    orders[0].origin = "Changed after plan"; orders[0].save(update_fields=["origin", "updated_at"])
    option = plan.data["options"][0]
    confirmed = client.post(f"/api/v1/fleet/dispatch-plans/{plan.data['plan_id']}/confirm", {
        "option_id": option["option_id"], "fingerprint": plan.data["fingerprint"], "trip_number": "STALE-TRIP",
    }, format="json")
    assert confirmed.status_code == 409
    assert not FleetTrip.objects.filter(tenant=tenant, trip_number="STALE-TRIP").exists()


@pytest.mark.django_db
def test_dispatch_batch_splits_incompatible_shipments_across_trucks_atomically(dispatch_workspace):
    tenant, _, client, _, _, _, orders, starts_at, ends_at = dispatch_workspace
    orders[0].required_vehicle_type = "RIGID"; orders[0].save(update_fields=["required_vehicle_type", "updated_at"])
    orders[1].required_vehicle_type = "TANKER"; orders[1].save(update_fields=["required_vehicle_type", "updated_at"])
    FleetVehicle.objects.create(tenant=tenant, registration_number="PLAN-002", normalized_registration="PLAN-002",
        vehicle_type="TANKER", capacity=10, capacity_unit="TONNE")
    FleetDriver.objects.create(tenant=tenant, name="Second planning driver")
    plan = _plan(client, orders, starts_at, ends_at)
    assert plan.status_code == 201, plan.data
    option = next(option for option in plan.data["options"] if len(option.get("assignments", [])) == 2)
    assert not option["unserved_orders"]
    response = client.post(f"/api/v1/fleet/dispatch-plans/{plan.data['plan_id']}/confirm", {
        "option_id": option["option_id"], "fingerprint": plan.data["fingerprint"], "trip_number": "BATCH-TRIP",
    }, format="json")
    assert response.status_code == 201, response.data
    assert len(response.data["trips"]) == 2
    assert {trip["vehicle"]["registration_number"] for trip in response.data["trips"]} == {"PLAN-001", "PLAN-002"}
    assert FleetTripManifestItem.objects.filter(tenant=tenant, trip_id__in=[t["id"] for t in response.data["trips"]]).count() == 2
    assert FleetResourceReservation.objects.filter(tenant=tenant, trip_id__in=[t["id"] for t in response.data["trips"]], released_at__isnull=True).count() == 2
    replay = client.post(f"/api/v1/fleet/dispatch-plans/{plan.data['plan_id']}/confirm", {
        "option_id": option["option_id"], "fingerprint": plan.data["fingerprint"], "trip_number": "BATCH-TRIP",
    }, format="json")
    assert replay.status_code == 200 and len(replay.data["trips"]) == 2


@pytest.mark.django_db
def test_google_routes_provider_reorders_valid_stops_and_saves_route_snapshot(dispatch_workspace):
    tenant, _, client, _, _, _, orders, starts_at, ends_at = dispatch_workspace
    tenant.settings = {**tenant.settings, "fleet_controls": {"route_eta_enabled": True}}
    tenant.save(update_fields=["settings"])

    class FakeResponse:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def read(self):
            return json.dumps({"routes": [{"distanceMeters": 150000, "duration": "1800s",
                "legs": [{"distanceMeters": 50000, "duration": "600s"} for _ in range(3)],
                "optimizedIntermediateWaypointIndex": [0, 1],
                "polyline": {"encodedPolyline": "_p~iF~ps|U_ulLnnqC_mqNvxq`@"}}]}).encode()

    with patch.dict(os.environ, {"GOOGLE_MAPS_ROUTES_API_KEY": "test-key"}), \
            patch("fleet.dispatch_planning.urlopen", return_value=FakeResponse()):
        plan = _plan(client, orders, starts_at, ends_at)
        assert plan.status_code == 201, plan.data
        option = plan.data["options"][0]
        assert option["route"]["provider_status"] == "UPDATED"
        assert option["route"]["distance_kind"] == "GOOGLE_ROAD_ESTIMATE"
        assert option["route"]["distance_km"] == 150.0
        assert FleetDispatchRouteAttempt.objects.filter(tenant=tenant, plan_id=plan.data["plan_id"], status="UPDATED").count() == 1
        confirmed = client.post(f"/api/v1/fleet/dispatch-plans/{plan.data['plan_id']}/confirm", {
            "option_id": option["option_id"], "fingerprint": plan.data["fingerprint"], "trip_number": "GOOGLE-ROUTE-1",
        }, format="json")
    assert confirmed.status_code == 201, confirmed.data
    trip = FleetTrip.objects.get(tenant=tenant, trip_number="GOOGLE-ROUTE-1")
    saved_plan = FleetDispatchPlan.objects.get(tenant=tenant, id=plan.data["plan_id"])
    assert trip.route_distance_m == 150000 and trip.eta_source == "GOOGLE_TRAFFIC", saved_plan.selected_option
    assert FleetRouteSnapshot.objects.filter(tenant=tenant, trip=trip, distance_m=150000).exists()


@pytest.mark.django_db
def test_google_routes_failure_keeps_the_heuristic_proposal(dispatch_workspace):
    tenant, _, client, _, _, _, orders, starts_at, ends_at = dispatch_workspace
    tenant.settings = {**tenant.settings, "fleet_controls": {"route_eta_enabled": True}}
    tenant.save(update_fields=["settings"])
    with patch.dict(os.environ, {"GOOGLE_MAPS_ROUTES_API_KEY": "test-key"}), \
            patch("fleet.dispatch_planning.urlopen", side_effect=URLError("provider timeout")):
        plan = _plan(client, orders, starts_at, ends_at)
    assert plan.status_code == 201, plan.data
    route = plan.data["options"][0]["route"]
    assert route["provider_status"] == "FALLBACK"
    assert route["distance_kind"] == "STRAIGHT_LINE_LOWER_BOUND"
    assert any("local heuristic route remains in use" in warning for warning in route["warnings"])
    assert FleetDispatchRouteAttempt.objects.filter(tenant=tenant, plan_id=plan.data["plan_id"], status="FAILED").exists()

