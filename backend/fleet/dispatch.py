"""Read-only, explainable resource suggestions for an open transport order."""
import unicodedata
from uuid import UUID

from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import HasTenantMembership
from accounts.models import Membership
from .compatibility import load_compatibility
from .models import FleetDriver, FleetMaintenanceRecord, FleetTrip, FleetVehicle, TransportOrder


ACTIVE_ASSIGNMENT_STATUSES = [FleetTrip.Status.DRAFT, FleetTrip.Status.IN_PROGRESS, FleetTrip.Status.SUBMITTED]
HISTORY_STATUSES = [FleetTrip.Status.COMPLETED, FleetTrip.Status.SUBMITTED, FleetTrip.Status.APPROVED]
DISPATCH_ROLES = {Membership.Role.OWNER, Membership.Role.FINANCE, Membership.Role.PURCHASE,
                  Membership.Role.APPROVER, "FLEET"}


def _place_key(value):
    value = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return " ".join("".join(ch if ch.isalnum() else " " for ch in value).split())


class FleetDispatchRecommendations(APIView):
    """Suggest compatible, currently unassigned resources without dispatching them."""
    permission_classes = [HasTenantMembership]

    def get(self, request):
        if request.membership.role not in DISPATCH_ROLES:
            return Response({"error": "Fleet dispatch access required."}, status=403)
        order_id = request.query_params.get("order_id", "").strip()
        if not order_id:
            return Response({"error": "Choose an order to get dispatch suggestions."}, status=400)
        try:
            order_id = UUID(order_id)
        except ValueError:
            return Response({"error": "Choose a valid order ID."}, status=400)
        order = TransportOrder.objects.filter(tenant=request.tenant, id=order_id).select_related("customer").first()
        if order is None:
            return Response({"error": "Transport order not found in this workspace."}, status=404)
        if order.status != TransportOrder.Status.OPEN:
            return Response({"error": "Suggestions are available only for open, unassigned orders."}, status=409)

        busy = FleetTrip.objects.filter(tenant=request.tenant, status__in=ACTIVE_ASSIGNMENT_STATUSES)
        busy_vehicle_ids = set(busy.values_list("vehicle_id", flat=True))
        busy_driver_ids = set(busy.values_list("driver_id", flat=True))
        broken_vehicle_ids = set(FleetMaintenanceRecord.objects.filter(
            tenant=request.tenant, breakdown_at__isnull=False, returned_to_service_at__isnull=True,
        ).values_list("vehicle_id", flat=True))

        vehicles = list(FleetVehicle.objects.filter(
            tenant=request.tenant, status=FleetVehicle.Status.ACTIVE,
        ).order_by("registration_number")[:1000])
        drivers = list(FleetDriver.objects.filter(
            tenant=request.tenant, status=FleetDriver.Status.ACTIVE,
        ).order_by("name")[:1000])

        last_stops = {}
        for trip in FleetTrip.objects.filter(
            tenant=request.tenant, vehicle_id__in=[v.id for v in vehicles],
            status__in=HISTORY_STATUSES, delivery_at__isnull=False,
        ).select_related("transport_order").order_by("-delivery_at")[:3000]:
            if trip.vehicle_id not in last_stops:
                last_stops[trip.vehicle_id] = trip.destination or (
                    trip.transport_order.destination if trip.transport_order_id else ""
                )

        excluded = {"busy_vehicles": 0, "open_breakdowns": 0, "incompatible_vehicles": 0,
                    "busy_drivers": 0}
        suggestions = []
        order_origin = _place_key(order.origin)
        for vehicle in vehicles:
            if vehicle.id in busy_vehicle_ids:
                excluded["busy_vehicles"] += 1
                continue
            if vehicle.id in broken_vehicle_ids:
                excluded["open_breakdowns"] += 1
                continue
            fit, fit_reason = load_compatibility(vehicle, order)
            if fit is False:
                excluded["incompatible_vehicles"] += 1
                continue
            reasons = []
            warnings = []
            score = 70 if fit is True else 40
            reasons.append(fit_reason)
            if fit is None:
                warnings.append(fit_reason)
            last_stop = last_stops.get(vehicle.id)
            if order_origin and last_stop and _place_key(last_stop) == order_origin:
                score += 30
                reasons.append("Last recorded completed-trip destination matches this order's pickup text.")
            elif last_stop:
                warnings.append("Last recorded delivery location differs from the pickup; repositioning distance is not calculated.")
            else:
                warnings.append("No completed-trip destination is recorded for this truck, so proximity could not be ranked.")
            suggestions.append({
                "vehicle_id": str(vehicle.id),
                "registration_number": vehicle.registration_number,
                "vehicle_type": vehicle.vehicle_type,
                "capacity": str(vehicle.capacity) if vehicle.capacity is not None else None,
                "capacity_unit": vehicle.capacity_unit,
                "score": score,
                "score_basis": "Configured type/capacity compatibility (70 points) and exact text match to the last recorded delivery location (30 points).",
                "reasons": reasons,
                "warnings": warnings,
            })
        suggestions.sort(key=lambda row: (-row["score"], row["registration_number"]))

        available_drivers = []
        for driver in drivers:
            if driver.id in busy_driver_ids:
                excluded["busy_drivers"] += 1
                continue
            available_drivers.append({"id": str(driver.id), "name": driver.name})

        return Response({
            "order": {"id": str(order.id), "order_number": order.order_number,
                      "origin": order.origin, "destination": order.destination},
            "vehicles": suggestions[:10],
            "drivers": available_drivers,
            "excluded": excluded,
            "automatically_assigned": False,
            "limitations": [
                "This is a rule-based shortlist, not a route solver. It uses text compatibility and recorded trip data only.",
                "Driver shifts, leave, endorsements, legal hours, live position, road distance, tolls, traffic and multi-stop load are not scored yet.",
                "Confirm the route and driver suitability before using the existing dispatch action; assignment rechecks resource conflicts.",
            ],
        })
