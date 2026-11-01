"""Multi-stop dispatch planning with deterministic, reviewable fallbacks."""
import hashlib
import json
import math
import os
import time
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from uuid import UUID
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Membership
from accounts.permissions import HasTenantMembership
from audit.models import AuditLog
from .compatibility import canonical_unit
from .models import (
    FleetDispatchPlan, FleetDispatchRouteAttempt, FleetDriver, FleetDriverSchedule, FleetMaintenanceRecord,
    FleetResourceReservation, FleetTrip, FleetTripManifestItem, FleetTripStop,
    FleetRouteProviderAttempt, FleetVehicle, TransportOrder,
)
from .serializers import FleetTripSerializer

EDIT_ROLES = {Membership.Role.OWNER, Membership.Role.FINANCE, Membership.Role.PURCHASE, "FLEET"}
READ_ROLES = EDIT_ROLES | {Membership.Role.APPROVER, Membership.Role.AUDITOR}
ACTIVE_TRIP_STATES = {FleetTrip.Status.DRAFT, FleetTrip.Status.IN_PROGRESS, FleetTrip.Status.SUBMITTED}
CAPACITY_CONVERSION = {("KG", "TONNE"): Decimal("0.001"), ("TONNE", "KG"): Decimal("1000")}
MAX_PLAN_ORDERS = 20
PLAN_LIFETIME = timedelta(minutes=20)


def _decimal(value, field, *, minimum=None, maximum=None):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{field} must be a valid number.")
    if not result.is_finite() or (minimum is not None and result < minimum) or (maximum is not None and result > maximum):
        raise ValueError(f"{field} is outside the supported range.")
    return result


def _datetime(value, field):
    parsed = parse_datetime(str(value or ""))
    if parsed is None:
        raise ValueError(f"{field} must be an ISO date and time with a timezone.")
    if timezone.is_naive(parsed):
        raise ValueError(f"{field} must include a timezone.")
    return parsed


def _distance_km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (float(a[0]), float(a[1]), float(b[0]), float(b[1])))
    h = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371.0088 * 2 * math.asin(min(1, math.sqrt(h)))


def _as_base_quantity(quantity, unit, capacity_unit):
    quantity = Decimal(str(quantity))
    unit, capacity_unit = canonical_unit(unit), canonical_unit(capacity_unit)
    if not unit or not capacity_unit:
        return None
    if unit == capacity_unit:
        return quantity
    factor = CAPACITY_CONVERSION.get((unit, capacity_unit))
    return quantity * factor if factor is not None else None


def _assigned_quantity(order):
    items = FleetTripManifestItem.objects.filter(tenant_id=order.tenant_id, order=order).exclude(
        status=FleetTripManifestItem.Status.CANCELLED,
    ).exclude(trip__status=FleetTrip.Status.CANCELLED)
    total = sum((row.quantity or Decimal("0") for row in items), Decimal("0"))
    if not items.exists():
        legacy = FleetTrip.objects.filter(tenant_id=order.tenant_id, transport_order=order).exclude(status=FleetTrip.Status.CANCELLED).exists()
        if legacy:
            return order.load_quantity or Decimal("0")
    return total


def _order_allocation(order, quantity):
    if order.load_quantity is None or not order.load_unit:
        raise ValueError(f"{order.order_number} needs a load quantity and unit before optimized dispatch.")
    remaining = order.load_quantity - _assigned_quantity(order)
    if remaining <= 0:
        raise ValueError(f"{order.order_number} has no unassigned load remaining.")
    quantity = _decimal(quantity, f"{order.order_number} quantity", minimum=Decimal("0.001"))
    if quantity > remaining:
        raise ValueError(f"{order.order_number} has only {remaining} {order.load_unit} unassigned.")
    return quantity


def _stop(order, kind, sequence, at_time, service_minutes):
    if kind == FleetTripStop.Kind.PICKUP:
        address, lat, lon, due = order.origin, order.origin_latitude, order.origin_longitude, order.pickup_due_at
    else:
        address, lat, lon, due = order.destination, order.destination_latitude, order.destination_longitude, order.delivery_due_at
    return {
        "order_id": str(order.id), "order_number": order.order_number, "kind": kind,
        "address": address, "latitude": str(lat) if lat is not None else None,
        "longitude": str(lon) if lon is not None else None,
        "window_end": due.isoformat() if due else None, "service_minutes": service_minutes,
        "planned_at": None, "sequence": sequence, "due_at": due,
    }


def _route_for_vehicle(orders, quantities, vehicle, starts_at, ends_at, speed_kmh):
    speed = float(speed_kmh)
    capacity_unit = canonical_unit(vehicle.capacity_unit)
    if vehicle.capacity is None or not capacity_unit:
        return None, "Truck capacity and unit must be configured."
    loads = {}
    for order in orders:
        if order.required_vehicle_type and vehicle.vehicle_type.strip().upper() != order.required_vehicle_type.strip().upper():
            return None, f"{order.order_number} requires vehicle type {order.required_vehicle_type}."
        load = _as_base_quantity(quantities[str(order.id)], order.load_unit, capacity_unit)
        if load is None:
            return None, f"{order.order_number} uses {order.load_unit}; it cannot be compared with truck capacity in {vehicle.capacity_unit}."
        if load <= 0 or load > vehicle.capacity:
            return None, f"{order.order_number} exceeds the truck's configured capacity."
        loads[str(order.id)] = load

    pending = {}
    for order in orders:
        pending[str(order.id)] = {
            "order": order, "quantity": loads[str(order.id)], "picked": False, "delivered": False,
            "pickup": _stop(order, FleetTripStop.Kind.PICKUP, 0, starts_at, 30),
            "delivery": _stop(order, FleetTripStop.Kind.DELIVERY, 0, starts_at, 30),
        }
    onboard = Decimal("0")
    current = None
    clock = starts_at
    total_distance = 0.0
    distance_known = True
    output = []
    impossible = []
    for _ in range(len(orders) * 2):
        candidates = []
        for key, item in pending.items():
            if not item["picked"] and onboard + item["quantity"] <= vehicle.capacity:
                candidates.append(item["pickup"])
            if item["picked"] and not item["delivered"]:
                candidates.append(item["delivery"])
        if not candidates:
            break
        def rank(stop):
            coord = (stop["latitude"], stop["longitude"]) if stop["latitude"] is not None else None
            distance = _distance_km(current, coord) if current and coord else None
            due = stop["due_at"].timestamp() if stop["due_at"] else float("inf")
            return (0 if distance is not None else 1, distance if distance is not None else 0, due, 0 if stop["kind"] == "DELIVERY" else 1, stop["order_number"])
        chosen = min(candidates, key=rank)
        coord = (chosen["latitude"], chosen["longitude"]) if chosen["latitude"] is not None else None
        if current and coord:
            leg_km = _distance_km(current, coord)
            total_distance += leg_km
            clock += timedelta(minutes=(leg_km / speed) * 60)
        elif current is None and coord:
            current = coord
        else:
            distance_known = False
        if chosen["due_at"] and coord and clock > chosen["due_at"]:
            impossible.append(f"{chosen['order_number']} {chosen['kind'].lower()} window is infeasible at the configured {speed_kmh:g} km/h planning speed.")
        chosen["planned_at"] = clock.isoformat()
        chosen["sequence"] = len(output) + 1
        output.append({key: value for key, value in chosen.items() if key != "due_at"})
        item = pending[chosen["order_id"]]
        if chosen["kind"] == FleetTripStop.Kind.PICKUP:
            item["picked"] = True
            onboard += item["quantity"]
        else:
            item["delivered"] = True
            onboard -= item["quantity"]
        current = coord or current
        clock += timedelta(minutes=chosen["service_minutes"])
    unserved = [item["order"].order_number for item in pending.values() if not item["delivered"]]
    if unserved:
        impossible.append("Capacity sequencing cannot carry every selected shipment in one route: " + ", ".join(unserved) + ".")
    if distance_known and clock > ends_at:
        impossible.append("The estimated route and service time exceed the selected dispatch window.")
    if impossible:
        return None, " ".join(impossible)
    warnings = []
    if not distance_known:
        warnings.append("Some stop coordinates are missing. Stop order uses due times and pickup-before-delivery; distance and window feasibility are unknown for those legs.")
    warnings.append("Distances are straight-line lower bounds from the first planned stop; truck road distance, traffic, tolls and restrictions are not represented by this fallback.")
    return {
        "stops": output,
        "distance_km": round(total_distance, 2) if distance_known else None,
        "distance_kind": "STRAIGHT_LINE_LOWER_BOUND" if distance_known else "UNKNOWN",
        "estimated_travel_minutes": round((clock - starts_at).total_seconds() / 60) if distance_known else None,
        "planning_speed_kmh": speed,
        "method": "NEAREST_NEIGHBOR_FALLBACK" if distance_known else "DUE_WINDOW_FALLBACK",
        "warnings": warnings,
        "unserved_orders": [],
    }, None


def _resource_conflict(tenant, vehicle, driver, starts_at, ends_at):
    reservations = FleetResourceReservation.objects.filter(tenant=tenant, released_at__isnull=True,
        starts_at__lt=ends_at, ends_at__gt=starts_at)
    if reservations.filter(vehicle=vehicle).exists():
        return "Truck has a confirmed dispatch reservation during this planning window."
    if reservations.filter(driver=driver).exists():
        return "Driver has a confirmed dispatch reservation during this planning window."
    trips = FleetTrip.objects.filter(tenant=tenant, status__in=ACTIVE_TRIP_STATES).filter(
        Q(vehicle=vehicle) | Q(driver=driver))
    for trip in trips.only("vehicle_id", "driver_id", "status", "starts_at", "ends_at"):
        if trip.status in {FleetTrip.Status.IN_PROGRESS, FleetTrip.Status.SUBMITTED}:
            if trip.vehicle_id == vehicle.id or trip.driver_id == driver.id:
                return "Truck or driver has a trip in progress or awaiting review."
        if not trip.starts_at or not trip.ends_at or (trip.starts_at < ends_at and trip.ends_at > starts_at):
            if trip.vehicle_id == vehicle.id or trip.driver_id == driver.id:
                return "Truck or driver already has a trip in this time window."
    if FleetMaintenanceRecord.objects.filter(tenant=tenant, vehicle=vehicle, breakdown_at__isnull=False,
        returned_to_service_at__isnull=True).exists():
        return "Truck has an open breakdown."
    return None


def _driver_schedule(driver, starts_at, ends_at, schedules=None):
    schedules = schedules if schedules is not None else list(FleetDriverSchedule.objects.filter(tenant_id=driver.tenant_id, driver=driver,
        active=True, starts_at__lt=ends_at, ends_at__gt=starts_at).order_by("starts_at"))
    blocking = [s for s in schedules if s.kind in {FleetDriverSchedule.Kind.LEAVE, FleetDriverSchedule.Kind.UNAVAILABLE}]
    if blocking:
        return False, "Driver has recorded leave or unavailable time in this window."
    shifts = [s for s in schedules if s.kind == FleetDriverSchedule.Kind.SHIFT]
    if shifts:
        if not any(s.starts_at <= starts_at and s.ends_at >= ends_at for s in shifts):
            return False, "No recorded driver shift covers the entire dispatch window."
        return True, "Driver shift covers the dispatch window."
    any_shift = any(s.kind == FleetDriverSchedule.Kind.SHIFT and timezone.localtime(s.starts_at).date() == timezone.localtime(starts_at).date()
        for s in schedules)
    if any_shift:
        return False, "A driver shift exists that day, but it does not cover this entire dispatch window."
    return None, "No driver shift is recorded for this date; working hours require dispatcher confirmation."


def _availability_snapshot(tenant, vehicles, drivers, starts_at, ends_at):
    vehicle_ids = {v.id for v in vehicles}
    driver_ids = {d.id for d in drivers}
    unavailable_vehicles, unavailable_drivers = set(), set()
    reservations = FleetResourceReservation.objects.filter(tenant=tenant, released_at__isnull=True,
        starts_at__lt=ends_at, ends_at__gt=starts_at).values_list("vehicle_id", "driver_id")
    for vehicle_id, driver_id in reservations:
        if vehicle_id in vehicle_ids: unavailable_vehicles.add(vehicle_id)
        if driver_id in driver_ids: unavailable_drivers.add(driver_id)
    trips = FleetTrip.objects.filter(tenant=tenant, status__in=ACTIVE_TRIP_STATES).only(
        "vehicle_id", "driver_id", "status", "starts_at", "ends_at")
    for trip in trips:
        overlap = (trip.status in {FleetTrip.Status.IN_PROGRESS, FleetTrip.Status.SUBMITTED}
            or not trip.starts_at or not trip.ends_at or (trip.starts_at < ends_at and trip.ends_at > starts_at))
        if overlap:
            if trip.vehicle_id in vehicle_ids: unavailable_vehicles.add(trip.vehicle_id)
            if trip.driver_id in driver_ids: unavailable_drivers.add(trip.driver_id)
    broken_vehicles = set(FleetMaintenanceRecord.objects.filter(tenant=tenant,
        vehicle_id__in=vehicle_ids, breakdown_at__isnull=False, returned_to_service_at__isnull=True).values_list("vehicle_id", flat=True))
    schedule_rows = FleetDriverSchedule.objects.filter(tenant=tenant, driver_id__in=driver_ids, active=True).filter(
        Q(starts_at__lt=ends_at, ends_at__gt=starts_at) |
        Q(kind=FleetDriverSchedule.Kind.SHIFT, starts_at__date=timezone.localtime(starts_at).date())
    ).order_by("starts_at")
    schedules = {}
    for row in schedule_rows: schedules.setdefault(row.driver_id, []).append(row)
    return unavailable_vehicles, unavailable_drivers, broken_vehicles, schedules


def _fingerprint(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _plan_option_id(vehicle_id, driver_id):
    return hashlib.sha256(f"{vehicle_id}:{driver_id}".encode()).hexdigest()[:24]


def _build_fleet_assignment(orders, quantities, vehicles, drivers, schedules_by_driver,
                            starts_at, ends_at, speed, strategy):
    """Greedy bounded batch assignment; each truck/driver appears in at most one trip."""
    def quantity_key(order):
        return Decimal(str(quantities[str(order.id)]))

    ordered = sorted(orders, key=lambda order: (
        order.delivery_due_at.timestamp() if order.delivery_due_at else float("inf"),
        -quantity_key(order), order.order_number))
    if strategy == "largest_first":
        ordered.sort(key=lambda order: (-quantity_key(order),
            order.pickup_due_at.timestamp() if order.pickup_due_at else float("inf"), order.order_number))
    elif strategy == "reverse_due":
        ordered.reverse()

    eligible = []
    for driver in drivers:
        known, reason = _driver_schedule(driver, starts_at, ends_at, schedules_by_driver.get(driver.id, []))
        if known is not False:
            eligible.append({"driver": driver, "shift_known": known, "shift_reason": reason})
    groups, used_vehicles, used_drivers, unserved = [], set(), set(), []
    for order in ordered:
        candidates = []
        for group in groups:
            route, reason = _route_for_vehicle(group["orders"] + [order], quantities,
                group["vehicle"], starts_at, ends_at, speed)
            if reason:
                continue
            old_distance, new_distance = group["route"]["distance_km"], route["distance_km"]
            incremental = (new_distance - old_distance) if new_distance is not None and old_distance is not None else float("inf")
            capacity = Decimal(str(group["vehicle"].capacity or "0"))
            combined_load = sum((_as_base_quantity(quantity_key(row), row.load_unit, group["vehicle"].capacity_unit) or Decimal("0")
                for row in group["orders"] + [order]), Decimal("0"))
            utilization = float(combined_load / capacity) if capacity else 0
            primary, secondary = incremental, -utilization
            if strategy == "capacity_fit":
                primary, secondary = -utilization, new_distance if new_distance is not None else float("inf")
            # Existing trips are preferred when they can take the shipment without worsening feasibility.
            candidates.append((primary, secondary, group["vehicle"].registration_number,
                group["driver"].name, group, route))
        if len(groups) < min(len(vehicles), len(eligible)):
            for vehicle in vehicles:
                if vehicle.id in used_vehicles:
                    continue
                route, reason = _route_for_vehicle([order], quantities, vehicle, starts_at, ends_at, speed)
                if reason:
                    continue
                driver_row = next((row for row in eligible if row["driver"].id not in used_drivers), None)
                if not driver_row:
                    break
                distance = route["distance_km"] if route["distance_km"] is not None else float("inf")
                capacity = Decimal(str(vehicle.capacity or "0"))
                load = _as_base_quantity(quantity_key(order), order.load_unit, vehicle.capacity_unit)
                utilization = float(load / capacity) if load is not None and capacity else 0
                rank = (distance if strategy != "capacity_fit" else -utilization,
                    -utilization if strategy != "capacity_fit" else distance,
                    vehicle.registration_number, driver_row["driver"].name)
                group = {"vehicle": vehicle, "driver": driver_row["driver"],
                    "shift_known": driver_row["shift_known"], "shift_reason": driver_row["shift_reason"],
                    "orders": [order]}
                candidates.append((*rank, group, route))
        if not candidates:
            unserved.append({"order_id": str(order.id), "order_number": order.order_number,
                "quantity": quantities[str(order.id)], "reasons": [
                    "No unused active truck/driver pair can take this shipment within the selected window."]})
            continue
        chosen = min(candidates, key=lambda row: row[:4])
        group, route = chosen[4], chosen[5]
        if group not in groups:
            groups.append(group)
            used_vehicles.add(group["vehicle"].id)
            used_drivers.add(group["driver"].id)
        group["orders"] = group["orders"] if group["orders"][-1] is order else group["orders"] + [order]
        group["route"] = route

    assignments = []
    for group in groups:
        vehicle, driver, route = group["vehicle"], group["driver"], group["route"]
        warnings = list(route["warnings"])
        warnings.append(group["shift_reason"])
        warnings.append("This assignment is a proposal; confirm the complete batch before dispatch.")
        components = {"capacity_fit": 40, "availability": 20 if group["shift_known"] else 10,
            "on_time_window_fit": 20 if route["distance_km"] is not None else 10,
            "route_efficiency": 20 if route["distance_km"] is not None else 10}
        assignments.append({"vehicle_id": str(vehicle.id), "vehicle": vehicle.registration_number,
            "driver_id": str(driver.id), "driver": driver.name,
            "order_ids": [str(order.id) for order in group["orders"]],
            "score": sum(components.values()), "score_components": components,
            "route": route, "warnings": warnings})
    if not assignments:
        return None, unserved
    distance_values = [row["route"]["distance_km"] for row in assignments]
    all_known = all(value is not None for value in distance_values)
    stops = [stop for assignment in assignments for stop in assignment["route"]["stops"]]
    combined_route = {"stops": stops, "distance_km": round(sum(distance_values), 2) if all_known else None,
        "distance_kind": "STRAIGHT_LINE_LOWER_BOUND" if all_known else "UNKNOWN",
        "estimated_travel_minutes": max((row["route"]["estimated_travel_minutes"] or 0 for row in assignments), default=0) if all_known else None,
        "method": "GREEDY_MULTI_TRUCK_FALLBACK", "warnings": [warning for row in assignments for warning in row["warnings"]],
        "unserved_orders": unserved}
    signature = ":".join(f"{row['vehicle_id']}:{row['driver_id']}:{','.join(row['order_ids'])}" for row in assignments)
    option = {"option_id": hashlib.sha256(signature.encode()).hexdigest()[:24],
        "assignments": assignments, "unserved_orders": unserved,
        "vehicle": " · ".join(row["vehicle"] for row in assignments),
        "driver": " · ".join(row["driver"] for row in assignments),
        "vehicle_id": assignments[0]["vehicle_id"], "driver_id": assignments[0]["driver_id"],
        "route": combined_route, "score_components": {},
        "score": round(sum(row["score"] for row in assignments) / len(assignments)),
        "warnings": combined_route["warnings"]}
    return option, unserved


def _google_waypoint(stop):
    if stop.get("latitude") is not None and stop.get("longitude") is not None:
        return {"location": {"latLng": {"latitude": float(stop["latitude"]), "longitude": float(stop["longitude"])}}}
    if stop.get("address"):
        return {"address": stop["address"]}
    raise ValueError("MISSING_STOP_LOCATION")


def _claim_dispatch_route_attempt(plan, assignment_index):
    """Claim provider budget briefly; no database locks remain held during network I/O."""
    now = timezone.now()
    with transaction.atomic():
        type(plan.tenant).objects.select_for_update().get(pk=plan.tenant_id)
        recent_cutoff = now - timedelta(hours=24)
        try:
            budget = max(0, int(os.environ.get("GOOGLE_ROUTES_DAILY_REQUEST_BUDGET", "1000")))
        except (TypeError, ValueError):
            budget = 1000
        dispatch_attempts = FleetDispatchRouteAttempt.objects.filter(tenant_id=plan.tenant_id,
            requested_at__gte=recent_cutoff)
        tracking_attempts = FleetRouteProviderAttempt.objects.filter(tenant_id=plan.tenant_id,
            requested_at__gte=recent_cutoff)
        used = dispatch_attempts.count() + tracking_attempts.count()
        if budget == 0 or used >= budget:
            return None, "BUDGET_EXCEEDED"
        recent_failures = list(dispatch_attempts.order_by("-requested_at").values_list("requested_at", "status")[:3])
        recent_failures += list(tracking_attempts.order_by("-requested_at").values_list("requested_at", "status")[:3])
        recent_failures.sort(key=lambda row: row[0], reverse=True)
        latest_three = recent_failures[:3]
        if len(latest_three) == 3 and all(status == "FAILED" for _, status in latest_three) and now - latest_three[0][0] < timedelta(minutes=15):
            return None, "CIRCUIT_OPEN"
        attempt = FleetDispatchRouteAttempt.objects.create(tenant_id=plan.tenant_id,
            plan=plan, assignment_index=assignment_index)
        return attempt, None


def _provider_route(route, vehicle, orders_by_id, quantities, starts_at, api_key):
    stops = route.get("stops", [])
    if len(stops) < 2:
        raise ValueError("INSUFFICIENT_STOPS")
    # Compute Routes accepts a bounded waypoint list; larger manifests use the safe local fallback.
    if len(stops) - 2 > 25:
        raise ValueError("WAYPOINT_LIMIT")
    body = {"origin": _google_waypoint(stops[0]), "destination": _google_waypoint(stops[-1]),
        "intermediates": [_google_waypoint(stop) for stop in stops[1:-1]],
        "travelMode": "DRIVE", "routingPreference": "TRAFFIC_AWARE",
        "optimizeWaypointOrder": True, "departureTime": starts_at.isoformat().replace("+00:00", "Z")}
    request = Request("https://routes.googleapis.com/directions/v2:computeRoutes",
        data=json.dumps(body).encode("utf-8"), method="POST", headers={
            "Content-Type": "application/json", "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "routes.distanceMeters,routes.duration,routes.legs.distanceMeters,routes.legs.duration,routes.polyline.encodedPolyline,routes.optimizedIntermediateWaypointIndex"})
    started = time.monotonic()
    with urlopen(request, timeout=8) as response:
        status_code = response.status
        payload = json.loads(response.read())
    elapsed_ms = max(0, int((time.monotonic() - started) * 1000))
    candidate = payload["routes"][0]
    order = candidate.get("optimizedIntermediateWaypointIndex", [])
    if len(order) != len(stops) - 2 or sorted(order) != list(range(len(stops) - 2)):
        raise ValueError("INVALID_WAYPOINT_ORDER")
    reordered = [stops[0]] + [stops[index + 1] for index in order] + [stops[-1]]
    legs = candidate["legs"]
    if len(legs) != len(reordered) - 1:
        raise ValueError("INVALID_ROUTE_LEGS")
    try:
        distance_m = int(candidate["distanceMeters"])
        duration_seconds = int(float(candidate["duration"].removesuffix("s")))
        leg_seconds = [int(float(leg["duration"].removesuffix("s"))) for leg in legs]
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ValueError("INVALID_RESPONSE")
    if not (0 <= distance_m <= 50_000_000 and 0 <= duration_seconds <= 2_592_000 and all(0 <= s <= 2_592_000 for s in leg_seconds)):
        raise ValueError("INVALID_RESPONSE")
    onboard, picked, delivered = Decimal("0"), set(), set()
    clock = starts_at
    for index, stop in enumerate(reordered):
        if index:
            previous = reordered[index - 1]
            clock += timedelta(minutes=int(previous.get("service_minutes", 0)))
            clock += timedelta(seconds=leg_seconds[index - 1])
        stop["sequence"] = index + 1
        stop["planned_at"] = clock.isoformat()
        due = parse_datetime(stop.get("window_end") or "")
        if due and clock > due:
            raise ValueError("PROVIDER_WINDOW_INFEASIBLE")
        order_id = stop["order_id"]
        order = orders_by_id[order_id]
        quantity = _as_base_quantity(quantities[order_id], order.load_unit, vehicle.capacity_unit)
        if quantity is None:
            raise ValueError("INCOMPATIBLE_CAPACITY_UNIT")
        if stop["kind"] == FleetTripStop.Kind.PICKUP:
            if order_id in picked:
                raise ValueError("DUPLICATE_PICKUP")
            picked.add(order_id); onboard += quantity
            if onboard > vehicle.capacity:
                raise ValueError("PROVIDER_CAPACITY_INFEASIBLE")
        elif stop["kind"] == FleetTripStop.Kind.DELIVERY:
            if order_id not in picked or order_id in delivered:
                raise ValueError("PROVIDER_PICKUP_DELIVERY_ORDER_INVALID")
            delivered.add(order_id); onboard -= quantity
        else:
            raise ValueError("INVALID_STOP_KIND")
    if picked != delivered:
        raise ValueError("INCOMPLETE_PROVIDER_ROUTE")
    encoded = candidate.get("polyline", {}).get("encodedPolyline")
    if not encoded:
        raise ValueError("MISSING_ROUTE_POLYLINE")
    return {**route, "stops": reordered, "distance_km": round(distance_m / 1000, 2),
        "distance_kind": "GOOGLE_ROAD_ESTIMATE", "estimated_travel_minutes": round(duration_seconds / 60),
        "method": "GOOGLE_ROUTES_TRAFFIC_AWARE", "provider": "GOOGLE_ROUTES",
        "provider_status": "UPDATED", "distance_m": distance_m,
        "duration_seconds": duration_seconds, "encoded_polyline": encoded,
        "warnings": list(route.get("warnings", [])) + [
            "Google Routes optimized the stop sequence and estimated road distance and traffic-aware duration. Truck height/weight restrictions, tolls, and driver-hours are not certified."]}, status_code, elapsed_ms


def _validate_provider_route(route, orders, quantities, vehicle, starts_at, ends_at):
    if route.get("provider") != "GOOGLE_ROUTES" or not route.get("encoded_polyline"):
        return "The provider route is incomplete."
    loads = {}
    for order in orders:
        if order.required_vehicle_type and vehicle.vehicle_type.strip().upper() != order.required_vehicle_type.strip().upper():
            return f"{order.order_number} no longer matches this truck type."
        load = _as_base_quantity(quantities[str(order.id)], order.load_unit, vehicle.capacity_unit)
        if load is None or vehicle.capacity is None or load > vehicle.capacity:
            return f"{order.order_number} no longer fits this truck's configured capacity."
        loads[str(order.id)] = load
    onboard, picked, delivered = Decimal("0"), set(), set()
    stops = route.get("stops", [])
    if len(stops) != 2 * len(orders):
        return "The provider route no longer has one pickup and delivery per shipment."
    for stop in stops:
        order_id = stop.get("order_id")
        if order_id not in loads:
            return "The provider route contains an unknown shipment."
        at = parse_datetime(stop.get("planned_at") or "")
        if at is None or timezone.is_naive(at) or at < starts_at or at > ends_at:
            return "A provider stop falls outside the confirmed dispatch window."
        due = parse_datetime(stop.get("window_end") or "")
        if due and at > due:
            return "A provider stop misses its shipment time window."
        if stop.get("kind") == FleetTripStop.Kind.PICKUP:
            if order_id in picked:
                return "The provider route repeats a shipment pickup."
            picked.add(order_id); onboard += loads[order_id]
            if onboard > vehicle.capacity:
                return "The provider stop order exceeds the truck's load capacity."
        elif stop.get("kind") == FleetTripStop.Kind.DELIVERY:
            if order_id not in picked or order_id in delivered:
                return "The provider route places a delivery before its pickup."
            delivered.add(order_id); onboard -= loads[order_id]
        else:
            return "The provider route contains an unsupported stop kind."
    return None if picked == delivered else "The provider route leaves shipment work incomplete."


def _refine_plan_routes(plan, snapshot, vehicles, orders):
    controls = plan.tenant.settings.get("fleet_controls", {})
    enabled = controls.get("route_eta_enabled", False)
    api_key = os.environ.get("GOOGLE_MAPS_ROUTES_API_KEY", "")
    orders_by_id = {str(order.id): order for order in orders}
    vehicles_by_id = {str(vehicle.id): vehicle for vehicle in vehicles}
    if not enabled or not api_key:
        status = "DISABLED" if not enabled else "NOT_CONFIGURED"
        for option in snapshot["options"]:
            assignments = option.get("assignments") or [{"vehicle_id": option.get("vehicle_id"), "route": option["route"]}]
            for assignment in assignments:
                assignment["route"]["provider_status"] = status
        return snapshot
    attempt_index = 0
    for option in snapshot["options"][:3]:
        assignments = option.get("assignments") or [{"vehicle_id": option.get("vehicle_id"), "route": option["route"]}]
        for assignment in assignments:
            if attempt_index >= 3:
                assignment["route"]["provider_status"] = "PLAN_REQUEST_LIMIT"
                continue
            attempt_index += 1
            route = assignment["route"]
            vehicle = vehicles_by_id.get(assignment["vehicle_id"])
            if vehicle is None:
                route["provider_status"] = "FALLBACK"
                continue
            attempt, blocked = _claim_dispatch_route_attempt(plan, attempt_index)
            if blocked:
                route["provider_status"] = blocked
                route["warnings"] = list(route.get("warnings", [])) + ["Google Routes was not called because the tenant request budget or provider circuit breaker blocked it."]
                continue
            started = time.monotonic()
            try:
                assignment_quantities = {row["id"]: row["quantity"] for row in snapshot["input_orders"]}
                refined, response_code, elapsed = _provider_route(route, vehicle, orders_by_id,
                    assignment_quantities, plan.starts_at, api_key)
                assignment["route"] = refined
                if not option.get("assignments"):
                    option["route"] = refined
                attempt.status = FleetDispatchRouteAttempt.Status.UPDATED
                attempt.response_code = response_code
                attempt.distance_m = refined["distance_m"]
                attempt.duration_seconds = refined["duration_seconds"]
            except (HTTPError, URLError, OSError, ValueError, KeyError, IndexError, TypeError) as exc:
                attempt.status = FleetDispatchRouteAttempt.Status.FAILED
                attempt.response_code = getattr(exc, "code", None)
                attempt.error_code = str(exc)[:32] if isinstance(exc, ValueError) else "PROVIDER_ERROR"
                route["provider_status"] = "FALLBACK"
                route["warnings"] = list(route.get("warnings", [])) + [
                    "Google Routes was unavailable or its route violated capacity, pickup order, or delivery windows; the local heuristic route remains in use."]
            assignment["warnings"] = list(assignment["route"].get("warnings", []))
            if not option.get("assignments"):
                option["warnings"] = assignment["warnings"]
            attempt.duration_ms = max(0, int((time.monotonic() - started) * 1000))
            attempt.completed_at = timezone.now()
            attempt.save(update_fields=["status", "response_code", "distance_m", "duration_seconds",
                "error_code", "duration_ms", "completed_at"])
        if option.get("assignments"):
            routes = [row["route"] for row in option["assignments"]]
            values = [route.get("distance_km") for route in routes]
            option["route"]["distance_km"] = round(sum(values), 2) if all(value is not None for value in values) else None
            option["route"]["estimated_travel_minutes"] = max((route.get("estimated_travel_minutes") or 0 for route in routes), default=0)
            option["route"]["stops"] = [stop for route in routes for stop in route["stops"]]
            option["route"]["warnings"] = [warning for route in routes for warning in route.get("warnings", [])]
            option["warnings"] = option["route"]["warnings"]
    return snapshot


class FleetDispatchPlanOptimize(APIView):
    permission_classes = [HasTenantMembership]

    def post(self, request):
        if request.membership.role not in EDIT_ROLES:
            return Response({"error": "Fleet dispatch edit access required."}, status=403)
        if not isinstance(request.data, dict) or set(request.data) - {"allocations", "starts_at", "ends_at", "request_key"}:
            return Response({"error": "Provide allocations, starts_at, ends_at, and request_key only."}, status=400)
        allocations_raw = request.data.get("allocations")
        if not isinstance(allocations_raw, list) or not allocations_raw or len(allocations_raw) > MAX_PLAN_ORDERS:
            return Response({"error": f"Select 1–{MAX_PLAN_ORDERS} open orders for one dispatch plan."}, status=400)
        try:
            starts_at = _datetime(request.data.get("starts_at"), "starts_at")
            ends_at = _datetime(request.data.get("ends_at"), "ends_at")
            if ends_at <= starts_at or ends_at - starts_at > timedelta(days=2):
                raise ValueError("The dispatch window must be positive and no longer than 48 hours.")
            request_key = UUID(str(request.data.get("request_key", "")))
        except (ValueError, TypeError) as exc:
            return Response({"error": str(exc) or "request_key must be a valid UUID."}, status=400)
        order_ids = []
        quantities = {}
        try:
            for row in allocations_raw:
                if not isinstance(row, dict) or set(row) != {"order_id", "quantity"}:
                    raise ValueError("Each allocation must contain order_id and quantity.")
                order_id = str(UUID(str(row["order_id"])))
                if order_id in quantities:
                    raise ValueError("An order can appear only once in a dispatch plan.")
                order_ids.append(order_id)
                quantities[order_id] = str(_decimal(row["quantity"], "quantity", minimum=Decimal("0.001")))
        except (ValueError, TypeError) as exc:
            return Response({"error": str(exc)}, status=400)
        orders = list(TransportOrder.objects.filter(tenant=request.tenant, id__in=order_ids).select_related("customer").order_by("id"))
        if len(orders) != len(order_ids):
            return Response({"error": "One or more selected orders were not found in this workspace."}, status=404)
        try:
            for order in orders:
                if order.status not in {TransportOrder.Status.OPEN, TransportOrder.Status.PARTIALLY_ASSIGNED}:
                    raise ValueError(f"{order.order_number} is not open for dispatch.")
                quantities[str(order.id)] = str(_order_allocation(order, quantities[str(order.id)]))
        except ValueError as exc:
            return Response({"error": str(exc)}, status=409)

        input_data = {"starts_at": starts_at.isoformat(), "ends_at": ends_at.isoformat(),
            "orders": [{"id": str(o.id), "updated_at": o.updated_at.isoformat(), "quantity": quantities[str(o.id)],
                        "customer_id": str(o.customer_id), "pickup": o.origin, "delivery": o.destination}
                       for o in orders]}
        fingerprint = _fingerprint(input_data)
        old = FleetDispatchPlan.objects.filter(tenant=request.tenant, request_key=request_key).first()
        if old:
            if old.input_fingerprint != fingerprint:
                return Response({"error": "This request key was already used for a different dispatch plan."}, status=409)
            return Response({"plan_id": str(old.id), "status": old.status, "fingerprint": old.input_fingerprint,
                "expires_at": old.expires_at.isoformat(), **old.snapshot}, status=200)

        controls = request.tenant.settings.get("fleet_controls", {})
        try:
            speed = _decimal(controls.get("planning_speed_kmh", "40"), "planning speed", minimum=Decimal("10"), maximum=Decimal("100"))
        except ValueError:
            speed = Decimal("40")
        vehicles = list(FleetVehicle.objects.filter(tenant=request.tenant, status=FleetVehicle.Status.ACTIVE).order_by("registration_number")[:500])
        drivers = list(FleetDriver.objects.filter(tenant=request.tenant, status=FleetDriver.Status.ACTIVE).order_by("name")[:500])
        unavailable_vehicles, unavailable_drivers, broken_vehicles, schedules_by_driver = _availability_snapshot(
            request.tenant, vehicles, drivers, starts_at, ends_at)
        options = []
        unserved = []
        vehicle_failures = {}
        for vehicle in vehicles:
            if vehicle.id in unavailable_vehicles:
                vehicle_failures[vehicle.registration_number] = "Truck already has a dispatch during this planning window."
                continue
            if vehicle.id in broken_vehicles:
                vehicle_failures[vehicle.registration_number] = "Truck has an open breakdown."
                continue
            route, reason = _route_for_vehicle(orders, quantities, vehicle, starts_at, ends_at, speed)
            if reason:
                vehicle_failures[vehicle.registration_number] = reason
                continue
            for driver in drivers:
                if driver.id in unavailable_drivers:
                    continue
                shift_known, shift_reason = _driver_schedule(driver, starts_at, ends_at, schedules_by_driver.get(driver.id, []))
                if shift_known is False:
                    continue
                warnings = list(route["warnings"])
                if shift_known is None:
                    warnings.append(shift_reason)
                else:
                    warnings.append(shift_reason)
                warnings.append("This option is a proposal. Driver confirmation and dispatcher approval are still required.")
                components = {"capacity_fit": 40, "availability": 20 if shift_known else 10,
                    "on_time_window_fit": 20 if route["distance_km"] is not None else 10,
                    "route_efficiency": 20 if route["distance_km"] is not None else 10}
                score = sum(components.values())
                options.append({"option_id": _plan_option_id(vehicle.id, driver.id),
                    "vehicle_id": str(vehicle.id), "vehicle": vehicle.registration_number,
                    "driver_id": str(driver.id), "driver": driver.name, "score": score,
                    "score_components": components, "route": route, "warnings": warnings})
        if not options:
            for order in orders:
                reasons = list(vehicle_failures.values())[:5]
                if not vehicles:
                    reasons.append("No active truck is configured.")
                if not drivers:
                    reasons.append("No active driver is configured.")
                if not reasons:
                    reasons.append("No vehicle and driver pair is available for the selected time window.")
                unserved.append({"order_id": str(order.id), "order_number": order.order_number,
                                 "quantity": quantities[str(order.id)], "reasons": reasons})
        else:
            route_distances = [option["route"]["distance_km"] for option in options if option["route"]["distance_km"] is not None]
            if route_distances:
                best_distance = max(min(route_distances), 0.01)
                for option in options:
                    distance = option["route"]["distance_km"]
                    if distance is not None:
                        option["score_components"]["route_efficiency"] = max(0, round(20 * best_distance / max(distance, 0.01)))
                        option["score"] = sum(option["score_components"].values())
            options.sort(key=lambda x: (-x["score"], x["route"]["distance_km"] if x["route"]["distance_km"] is not None else float("inf"), x["vehicle"], x["driver"]))
        eligible_vehicles = [vehicle for vehicle in vehicles if vehicle.id not in unavailable_vehicles and vehicle.id not in broken_vehicles]
        eligible_drivers = [driver for driver in drivers if driver.id not in unavailable_drivers]
        for strategy in ("due", "largest_first", "capacity_fit"):
            bundle, bundle_unserved = _build_fleet_assignment(orders, quantities, eligible_vehicles,
                eligible_drivers, schedules_by_driver, starts_at, ends_at, speed, strategy)
            if not bundle:
                continue
            if len(bundle["assignments"]) > 1 or bundle_unserved:
                bundle["strategy"] = strategy
                options.append(bundle)
                if not unserved:
                    unserved = bundle_unserved
        # Keep only distinct fleet plans and return a useful bounded set.
        distinct = {}
        for option in options:
            distinct.setdefault(option["option_id"], option)
        options = list(distinct.values())
        if options:
            unserved = [] if any(not option.get("unserved_orders") for option in options if option.get("assignments")) else unserved
        snapshot = {"options": options[:30], "unserved_orders": unserved,
            "method": "deterministic nearest-neighbor routes and greedy fleet batch assignment; no order was assigned",
            "ends_at": ends_at.isoformat(), "input_orders": input_data["orders"],
            "limitations": ["Multi-truck shipment grouping uses a bounded greedy heuristic; it is not a globally optimal fleet solver.",
                "When coordinates exist, distances are straight-line lower bounds from the first stop, not truck road routes. Missing coordinates leave distance and arrival feasibility unknown.",
                "Traffic, tolls, vehicle restrictions, driver endorsements and legal work-hour rules are not inferred. Add configured driver shifts and confirm legal suitability.",
                "The plan expires after 20 minutes. Confirmation rechecks order revisions, capacity, schedules, maintenance and competing reservations."],
            "order_count": len(orders)}
        status = FleetDispatchPlan.Status.PROPOSED if options else FleetDispatchPlan.Status.FAILED
        try:
            plan = FleetDispatchPlan.objects.create(tenant=request.tenant, request_key=request_key,
                input_fingerprint=fingerprint, status=status, snapshot=snapshot, starts_at=starts_at,
                expires_at=timezone.now()+PLAN_LIFETIME, created_by=request.user)
        except IntegrityError:
            plan = FleetDispatchPlan.objects.filter(tenant=request.tenant, request_key=request_key).first()
            if not plan or plan.input_fingerprint != fingerprint:
                return Response({"error": "This request key was claimed by a different plan."}, status=409)
        else:
            snapshot = _refine_plan_routes(plan, snapshot, vehicles, orders)
            plan.snapshot = snapshot
            plan.save(update_fields=["snapshot"])
        snapshot = plan.snapshot
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="FLEET_DISPATCH_PLAN_CREATED",
            object_type="FleetDispatchPlan", object_id=str(plan.id), metadata={"order_count": len(orders), "option_count": len(options), "method": "HEURISTIC"})
        return Response({"plan_id": str(plan.id), "status": plan.status, "fingerprint": plan.input_fingerprint,
            "expires_at": plan.expires_at.isoformat(), **snapshot}, status=201 if options else 200)


class FleetDispatchPlanConfirm(APIView):
    permission_classes = [HasTenantMembership]

    @transaction.atomic
    def post(self, request, plan_id):
        if request.membership.role not in EDIT_ROLES:
            return Response({"error": "Fleet dispatch edit access required."}, status=403)
        if not isinstance(request.data, dict) or set(request.data) != {"option_id", "fingerprint", "trip_number"}:
            return Response({"error": "Provide option_id, fingerprint, and trip_number."}, status=400)
        plan = FleetDispatchPlan.objects.select_for_update().filter(tenant=request.tenant, id=plan_id).first()
        if not plan:
            return Response({"error": "Dispatch plan not found."}, status=404)
        if plan.status == FleetDispatchPlan.Status.CONFIRMED and plan.confirmed_trip_id:
            trip_ids = plan.selected_option.get("confirmed_trip_ids", [str(plan.confirmed_trip_id)])
            trips = list(FleetTrip.objects.filter(tenant=request.tenant, id__in=trip_ids).order_by("trip_number"))
            trip = next((row for row in trips if row.id == plan.confirmed_trip_id), trips[0])
            return Response({"trip": FleetTripSerializer(trip, context={"tenant": request.tenant}).data,
                "trips": FleetTripSerializer(trips, many=True, context={"tenant": request.tenant}).data,
                "status": plan.status, "idempotent_replay": True}, status=200)
        if plan.status != FleetDispatchPlan.Status.PROPOSED:
            return Response({"error": "This dispatch plan is no longer available for confirmation."}, status=409)
        if plan.expires_at <= timezone.now():
            plan.status = FleetDispatchPlan.Status.EXPIRED
            plan.save(update_fields=["status"])
            return Response({"error": "This plan expired. Refresh the orders and generate new recommendations."}, status=409)
        if request.data["fingerprint"] != plan.input_fingerprint:
            return Response({"error": "The plan fingerprint changed. Refresh recommendations before confirming."}, status=409)
        option = next((x for x in plan.snapshot.get("options", []) if x["option_id"] == request.data["option_id"]), None)
        if not option:
            return Response({"error": "Choose a resource option from this plan."}, status=400)
        trip_number = str(request.data["trip_number"]).strip().upper()
        if not trip_number or len(trip_number) > 64:
            return Response({"error": "Enter a trip number up to 64 characters."}, status=400)
        # Lock in a consistent order before resource locks, then recheck the exact source revisions.
        order_ids = [row["id"] for row in plan.snapshot.get("input_orders", [])]
        if not order_ids:
            order_ids = [row["id"] for row in plan.snapshot.get("orders", [])]
        if not order_ids:
            return Response({"error": "The source order snapshot is missing. Create a fresh plan."}, status=409)
        orders = list(TransportOrder.objects.select_for_update().filter(tenant=request.tenant,
            id__in=order_ids).order_by("id"))
        if len(orders) != len(order_ids):
            return Response({"error": "One or more orders changed or were removed. Refresh the plan."}, status=409)
        saved_revisions = {row["id"]: row["updated_at"] for row in plan.snapshot.get("input_orders", [])}
        if any(saved_revisions.get(str(order.id)) != order.updated_at.isoformat() for order in orders):
            return Response({"error": "An order changed after planning. Refresh recommendations before dispatch."}, status=409)
        window_start = plan.starts_at
        window_end = _datetime(plan.snapshot["ends_at"], "ends_at")
        selected = {row["id"]: row for row in plan.snapshot["input_orders"]}
        for order in orders:
            if order.status not in {TransportOrder.Status.OPEN, TransportOrder.Status.PARTIALLY_ASSIGNED}:
                return Response({"error": f"{order.order_number} is no longer open for dispatch.", "refresh_required": True}, status=409)
            quantity = Decimal(selected[str(order.id)]["quantity"])
            try:
                _order_allocation(order, quantity)
            except ValueError as exc:
                return Response({"error": str(exc), "refresh_required": True}, status=409)
        controls = request.tenant.settings.get("fleet_controls", {})
        try:
            speed = _decimal(controls.get("planning_speed_kmh", "40"), "planning speed", minimum=Decimal("10"), maximum=Decimal("100"))
        except ValueError:
            speed = Decimal("40")
        specs = option.get("assignments") or [{"vehicle_id": option["vehicle_id"], "driver_id": option["driver_id"],
            "order_ids": order_ids, "route": option["route"]}]
        assigned_ids = [order_id for spec in specs for order_id in spec.get("order_ids", [])]
        if len(assigned_ids) != len(set(assigned_ids)) or set(assigned_ids) - set(order_ids):
            return Response({"error": "The selected proposal has an invalid shipment allocation."}, status=409)
        if not assigned_ids:
            return Response({"error": "The selected proposal does not assign any shipments."}, status=409)
        vehicle_ids = sorted({spec["vehicle_id"] for spec in specs})
        driver_ids = sorted({spec["driver_id"] for spec in specs})
        if len(vehicle_ids) != len(specs) or len(driver_ids) != len(specs):
            return Response({"error": "A proposal cannot schedule a truck or driver more than once in the same window."}, status=409)
        vehicles = {str(row.id): row for row in FleetVehicle.objects.select_for_update().filter(
            tenant=request.tenant, id__in=vehicle_ids, status=FleetVehicle.Status.ACTIVE).order_by("id")}
        drivers = {str(row.id): row for row in FleetDriver.objects.select_for_update().filter(
            tenant=request.tenant, id__in=driver_ids, status=FleetDriver.Status.ACTIVE).order_by("id")}
        if len(vehicles) != len(vehicle_ids) or len(drivers) != len(driver_ids):
            return Response({"error": "One or more selected trucks or drivers are no longer active."}, status=409)
        order_by_id = {str(order.id): order for order in orders}
        prepared = []
        trip_numbers = [trip_number if len(specs) == 1 else f"{trip_number}-{index:02d}" for index in range(1, len(specs)+1)]
        if any(len(number) > 64 for number in trip_numbers) or FleetTrip.objects.filter(
            tenant=request.tenant, trip_number__in=trip_numbers).exists():
            return Response({"error": "One or more generated trip numbers are already in use or too long."}, status=409)
        for index, spec in enumerate(specs):
            vehicle, driver = vehicles[spec["vehicle_id"]], drivers[spec["driver_id"]]
            conflict = _resource_conflict(request.tenant, vehicle, driver, window_start, window_end)
            if conflict:
                return Response({"error": conflict, "refresh_required": True}, status=409)
            shift_ok, shift_reason = _driver_schedule(driver, window_start, window_end)
            if shift_ok is False:
                return Response({"error": shift_reason, "refresh_required": True}, status=409)
            assigned_orders = [order_by_id[order_id] for order_id in spec["order_ids"]]
            route, route_error = _route_for_vehicle(assigned_orders,
                {order_id: selected[order_id]["quantity"] for order_id in spec["order_ids"]},
                vehicle, window_start, window_end, speed)
            if route_error:
                return Response({"error": "Truck suitability changed since planning: " + route_error,
                    "refresh_required": True}, status=409)
            provider_route = spec.get("route")
            if provider_route and provider_route.get("provider") == "GOOGLE_ROUTES":
                provider_error = _validate_provider_route(provider_route, assigned_orders,
                    {order_id: selected[order_id]["quantity"] for order_id in spec["order_ids"]},
                    vehicle, window_start, window_end)
                if provider_error:
                    return Response({"error": "The optimized road route is no longer feasible: " + provider_error,
                        "refresh_required": True}, status=409)
                route = provider_route
            lead = order_by_id[route["stops"][0]["order_id"]]
            prepared.append({"vehicle": vehicle, "driver": driver, "orders": assigned_orders,
                "route": route, "lead": lead, "trip_number": trip_numbers[index], "schedule_note": shift_reason})
        # Stable lock order: plan, orders, all trucks, all drivers, then one atomic write set.
        trips = []
        try:
            with transaction.atomic():
                for item in prepared:
                    vehicle, driver, route, lead = item["vehicle"], item["driver"], item["route"], item["lead"]
                    legacy_link = FleetTrip.objects.filter(tenant=request.tenant, transport_order=lead).exists()
                    trip = FleetTrip.objects.create(tenant=request.tenant, trip_number=item["trip_number"],
                        vehicle=vehicle, driver=driver, transport_order=None if legacy_link else lead, customer_reference=lead.customer_reference or lead.order_number,
                        origin=route["stops"][0]["address"], destination=route["stops"][-1]["address"],
                        starts_at=window_start, ends_at=window_end, status=FleetTrip.Status.DRAFT, created_by=request.user)
                    for order in item["orders"]:
                        quantity = Decimal(selected[str(order.id)]["quantity"])
                        FleetTripManifestItem.objects.create(tenant=request.tenant, trip=trip, order=order,
                            quantity=quantity, load_unit=order.load_unit, status=FleetTripManifestItem.Status.ASSIGNED)
                        allocated = _assigned_quantity(order)
                        order.status = TransportOrder.Status.PARTIALLY_ASSIGNED if allocated < (order.load_quantity or allocated) else TransportOrder.Status.ASSIGNED
                        order.save(update_fields=["status", "updated_at"])
                    for stop in route["stops"]:
                        order = order_by_id[stop["order_id"]]
                        FleetTripStop.objects.create(tenant=request.tenant, trip=trip, order=order,
                            sequence=stop["sequence"], kind=stop["kind"], address=stop["address"],
                            latitude=stop["latitude"], longitude=stop["longitude"],
                            window_end=stop["window_end"], service_minutes=stop["service_minutes"], planned_at=stop["planned_at"])
                    if route.get("provider") == "GOOGLE_ROUTES" and route.get("encoded_polyline"):
                        trip.route_distance_m = route["distance_m"]
                        trip.predicted_arrival_at = parse_datetime(route["stops"][-1]["planned_at"])
                        trip.eta_source = "GOOGLE_TRAFFIC"
                        trip.route_refreshed_at = timezone.now()
                        trip.save(update_fields=["route_distance_m", "predicted_arrival_at", "eta_source", "route_refreshed_at", "updated_at"])
                        from .routing import store_route_snapshot
                        store_route_snapshot(trip=trip, encoded_polyline=route["encoded_polyline"],
                            distance_m=route["distance_m"], duration_seconds=route["duration_seconds"],
                            destination=route["stops"][-1]["address"])
                    FleetResourceReservation.objects.create(tenant=request.tenant, trip=trip, vehicle=vehicle,
                        driver=driver, starts_at=window_start, ends_at=window_end)
                    trips.append(trip)
        except IntegrityError:
            return Response({"error": "One or more trips could not be committed. Refresh the plan and try again."}, status=409)
        trip = trips[0]
        plan.status = FleetDispatchPlan.Status.CONFIRMED
        plan.confirmed_trip = trip
        plan.confirmed_by = request.user
        plan.confirmed_at = timezone.now()
        plan.selected_option = {**option, "confirmed_trip_ids": [str(row.id) for row in trips]}
        plan.save(update_fields=["status", "confirmed_trip", "confirmed_by", "confirmed_at", "selected_option"])
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="FLEET_DISPATCH_PLAN_CONFIRMED",
            object_type="FleetTrip", object_id=str(trip.id), metadata={"plan_id": str(plan.id), "orders": assigned_ids,
                "assignments": [{"trip_id": str(row.id), "vehicle_id": str(row.vehicle_id), "driver_id": str(row.driver_id)} for row in trips],
                "unserved_orders": option.get("unserved_orders", [])})
        serialized = FleetTripSerializer(trips, many=True, context={"tenant": request.tenant}).data
        return Response({"status": plan.status, "trip": serialized[0], "trips": serialized,
            "unserved_orders": option.get("unserved_orders", [])}, status=201)


class FleetDriverSchedules(APIView):
    permission_classes = [HasTenantMembership]

    def get(self, request):
        if request.membership.role not in READ_ROLES:
            return Response({"error": "Fleet availability access required."}, status=403)
        rows = FleetDriverSchedule.objects.filter(tenant=request.tenant, active=True).select_related("driver").order_by("starts_at", "driver__name")[:2000]
        if request.query_params.get("driver_id"):
            rows = rows.filter(driver_id=request.query_params["driver_id"])
        return Response([{"id": str(row.id), "driver_id": str(row.driver_id), "driver": row.driver.name,
            "kind": row.kind, "starts_at": row.starts_at.isoformat(), "ends_at": row.ends_at.isoformat(),
            "note": row.note} for row in rows])

    @transaction.atomic
    def post(self, request):
        if request.membership.role not in EDIT_ROLES:
            return Response({"error": "Fleet availability edit access required."}, status=403)
        if set(request.data) - {"driver_id", "kind", "starts_at", "ends_at", "note"}:
            return Response({"error": "Unsupported schedule fields."}, status=400)
        try:
            driver_id = UUID(str(request.data.get("driver_id", "")))
            starts_at = _datetime(request.data.get("starts_at"), "starts_at")
            ends_at = _datetime(request.data.get("ends_at"), "ends_at")
            if ends_at <= starts_at or ends_at - starts_at > timedelta(days=2):
                raise ValueError("A schedule entry must be positive and no longer than 48 hours.")
        except (ValueError, TypeError) as exc:
            return Response({"error": str(exc)}, status=400)
        kind = request.data.get("kind")
        if kind not in FleetDriverSchedule.Kind.values:
            return Response({"error": "Choose SHIFT, LEAVE, or UNAVAILABLE."}, status=400)
        driver = FleetDriver.objects.select_for_update().filter(tenant=request.tenant, id=driver_id, status=FleetDriver.Status.ACTIVE).first()
        if not driver:
            return Response({"error": "Active driver not found in this workspace."}, status=404)
        if kind in {FleetDriverSchedule.Kind.LEAVE, FleetDriverSchedule.Kind.UNAVAILABLE}:
            if FleetResourceReservation.objects.filter(tenant=request.tenant, driver=driver, released_at__isnull=True,
                starts_at__lt=ends_at, ends_at__gt=starts_at).exists():
                return Response({"error": "This unavailable period overlaps a confirmed dispatch reservation."}, status=409)
        row = FleetDriverSchedule.objects.create(tenant=request.tenant, driver=driver, kind=kind,
            starts_at=starts_at, ends_at=ends_at, note=str(request.data.get("note", "")).strip()[:240], created_by=request.user)
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="FLEET_DRIVER_SCHEDULE_CREATED",
            object_type="FleetDriverSchedule", object_id=str(row.id), metadata={"driver_id": str(driver.id), "kind": kind,
                "starts_at": starts_at.isoformat(), "ends_at": ends_at.isoformat()})
        return Response({"id": str(row.id), "driver_id": str(driver.id), "driver": driver.name, "kind": kind,
            "starts_at": starts_at.isoformat(), "ends_at": ends_at.isoformat(), "note": row.note}, status=201)


class FleetDriverScheduleDetail(APIView):
    permission_classes = [HasTenantMembership]

    @transaction.atomic
    def delete(self, request, schedule_id):
        if request.membership.role not in EDIT_ROLES:
            return Response({"error": "Fleet availability edit access required."}, status=403)
        row = FleetDriverSchedule.objects.select_for_update().filter(tenant=request.tenant, id=schedule_id, active=True).first()
        if not row:
            return Response({"error": "Schedule entry not found."}, status=404)
        row.active = False
        row.save(update_fields=["active"])
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="FLEET_DRIVER_SCHEDULE_CANCELLED",
            object_type="FleetDriverSchedule", object_id=str(row.id), metadata={"reason": "Schedule entry removed by authorized operator."})
        return Response({"id": str(row.id), "active": False})


class FleetTripStopAction(APIView):
    """Record ordered pickup and delivery milestones for a planned multi-stop trip."""
    permission_classes = [HasTenantMembership]

    @transaction.atomic
    def post(self, request, trip_id, stop_id, action):
        if action not in {"arrive", "complete"}:
            return Response({"error": "Choose arrive or complete for a stop."}, status=404)
        trip = FleetTrip.objects.select_for_update().filter(tenant=request.tenant, id=trip_id).first()
        if not trip:
            return Response({"error": "Trip not found."}, status=404)
        is_assigned_driver = request.membership.role == Membership.Role.DRIVER and trip.driver.user_id == request.user.id
        if request.membership.role not in EDIT_ROLES and not is_assigned_driver:
            return Response({"error": "Fleet trip access required."}, status=403)
        if trip.status != FleetTrip.Status.IN_PROGRESS:
            return Response({"error": "Start the trip before updating route stops."}, status=409)
        stop = FleetTripStop.objects.select_for_update().select_related("order").filter(
            tenant=request.tenant, trip=trip, id=stop_id).first()
        if not stop:
            return Response({"error": "Stop not found on this trip."}, status=404)
        if action == "arrive":
            if stop.status == FleetTripStop.Status.ARRIVED:
                return Response({"id": str(stop.id), "status": stop.status, "actual_at": stop.actual_at.isoformat()})
            if stop.status != FleetTripStop.Status.PLANNED:
                return Response({"error": "Only a planned stop can be marked arrived."}, status=409)
            if FleetTripStop.objects.filter(tenant=request.tenant, trip=trip, sequence__lt=stop.sequence).exclude(
                status__in=[FleetTripStop.Status.COMPLETED, FleetTripStop.Status.SKIPPED]).exists():
                return Response({"error": "Complete the earlier route stop first."}, status=409)
            stop.status = FleetTripStop.Status.ARRIVED
            stop.actual_at = timezone.now()
            stop.save(update_fields=["status", "actual_at"])
            if stop.kind == FleetTripStop.Kind.PICKUP and stop.order.status in {TransportOrder.Status.ASSIGNED, TransportOrder.Status.PARTIALLY_ASSIGNED}:
                stop.order.status = TransportOrder.Status.LOADING
                stop.order.save(update_fields=["status", "updated_at"])
        else:
            if stop.status != FleetTripStop.Status.ARRIVED:
                return Response({"error": "Mark the stop arrived before completing it."}, status=409)
            stop.status = FleetTripStop.Status.COMPLETED
            stop.save(update_fields=["status"])
            if stop.kind == FleetTripStop.Kind.PICKUP:
                item = FleetTripManifestItem.objects.select_for_update().filter(tenant=request.tenant, trip=trip, order=stop.order).first()
                if item:
                    item.status = FleetTripManifestItem.Status.IN_TRANSIT
                    item.save(update_fields=["status"])
                stop.order.status = TransportOrder.Status.IN_TRANSIT
                stop.order.save(update_fields=["status", "updated_at"])
                if not FleetTripStop.objects.filter(tenant=request.tenant, trip=trip,
                    kind=FleetTripStop.Kind.PICKUP).exclude(status=FleetTripStop.Status.COMPLETED).exists():
                    trip.loaded_at = timezone.now()
                    trip.save(update_fields=["loaded_at", "updated_at"])
            else:
                item = FleetTripManifestItem.objects.select_for_update().filter(tenant=request.tenant, trip=trip, order=stop.order).first()
                if item:
                    item.status = FleetTripManifestItem.Status.DELIVERED
                    item.save(update_fields=["status"])
                delivered = sum((row.quantity or Decimal("0") for row in FleetTripManifestItem.objects.filter(
                    tenant=request.tenant, order=stop.order, status=FleetTripManifestItem.Status.DELIVERED)), Decimal("0"))
                assigned = sum((row.quantity or Decimal("0") for row in FleetTripManifestItem.objects.exclude(
                    status=FleetTripManifestItem.Status.CANCELLED).filter(tenant=request.tenant, order=stop.order).exclude(
                    trip__status=FleetTrip.Status.CANCELLED)), Decimal("0"))
                total = stop.order.load_quantity or assigned
                stop.order.status = (TransportOrder.Status.DELIVERED if delivered >= total else
                    TransportOrder.Status.PARTIALLY_DELIVERED if delivered > 0 else TransportOrder.Status.PARTIALLY_ASSIGNED)
                stop.order.save(update_fields=["status", "updated_at"])
        return Response({"id": str(stop.id), "status": stop.status,
            "actual_at": stop.actual_at.isoformat() if stop.actual_at else None,
            "next_stop_id": (str(next_stop.id) if (next_stop := FleetTripStop.objects.filter(
                tenant=request.tenant, trip=trip, sequence__gt=stop.sequence).order_by("sequence").first()) else None)})
