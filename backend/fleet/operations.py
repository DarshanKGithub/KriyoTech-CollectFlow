from decimal import Decimal
from datetime import date, datetime, time
from django.db import transaction
from django.db.models import Min, Max, Q, Sum
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
import csv
import io
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView
from accounts.permissions import HasTenantMembership
from .models import DockAppointment, FleetFuelBudget, FleetMaintenanceRecord, FleetTrip, FleetVehicle, ReturnLoadOffer, TransportInvoice, TripExpenseLine, TripRevenueLine
from .views import EDIT_ROLES, REVIEW_ROLES, audit, dock_appointment_data


def month_start_with_offset(day, offset):
    index = day.year * 12 + day.month - 1 + offset
    year, month_index = divmod(index, 12)
    return date(year, month_index + 1, 1)


def spend_direction(current, previous):
    if previous <= 0:
        return "NEW_ACTIVITY" if current > 0 else "INSUFFICIENT_DATA", None
    change = (current - previous) * 100 / previous
    direction = "RISING" if change > 5 else "FALLING" if change < -5 else "STABLE"
    return direction, str(change.quantize(Decimal("0.1")))


class FuelManagement(APIView):
    permission_classes = [HasTenantMembership]

    def access(self, request, write=False):
        return request.membership.role in (EDIT_ROLES if write else EDIT_ROLES | REVIEW_ROLES)

    def get(self, request):
        if not self.access(request):
            return Response({"error": "Fuel management access required."}, status=403)
        tenant = request.tenant
        try:
            start = date.fromisoformat(request.query_params.get("from", "")[:10]) if request.query_params.get("from") else timezone.localdate().replace(day=1)
            end = date.fromisoformat(request.query_params.get("to", "")[:10]) if request.query_params.get("to") else timezone.localdate()
        except ValueError:
            return Response({"error": "Use valid from/to dates in YYYY-MM-DD format."}, status=400)
        if end < start or (end - start).days > 366:
            return Response({"error": "Choose a date range up to 366 days, with the end date on or after the start date."}, status=400)
        lines = list(TripExpenseLine.objects.filter(tenant=tenant, category=TripExpenseLine.Category.FUEL,
            incurred_at__gte=start, incurred_at__lte=end, is_estimated=False).select_related(
                "trip__vehicle", "trip__driver").order_by("-incurred_at", "-created_at")[:5000])
        vehicle_totals = {str(vehicle.id): {"vehicle_id": str(vehicle.id), "registration_number": vehicle.registration_number,
            "spend": Decimal("0"), "litres": Decimal("0"), "entries": 0, "monthly_budget": None,
            "trip_budget": None, "expected_efficiency_km_per_litre": None}
            for vehicle in FleetVehicle.objects.filter(tenant=tenant).order_by("registration_number")}
        for line in lines:
            vehicle = line.trip.vehicle
            item = vehicle_totals[str(vehicle.id)]
            if line.status == TripExpenseLine.ReviewStatus.APPROVED:
                item["spend"] += line.amount
                if not line.is_refund:
                    item["litres"] += line.quantity_litres or Decimal("0")
            item["entries"] += 1
        budgets = {str(row.vehicle_id): row for row in FleetFuelBudget.objects.filter(tenant=tenant, vehicle_id__in=vehicle_totals)}
        month_start = timezone.localdate().replace(day=1)
        monthly_spend = {}
        for item in TripExpenseLine.objects.filter(tenant=tenant, category=TripExpenseLine.Category.FUEL,
                status=TripExpenseLine.ReviewStatus.APPROVED, is_estimated=False,
                incurred_at__gte=month_start, incurred_at__lte=timezone.localdate()).values("trip__vehicle_id", "is_refund").annotate(total=Sum("amount")):
            key = str(item["trip__vehicle_id"])
            monthly_spend[key] = monthly_spend.get(key, Decimal("0")) + (item["total"] or Decimal("0"))
        for vehicle_id, item in vehicle_totals.items():
            budget = budgets.get(vehicle_id)
            item["monthly_spend"] = str(monthly_spend.get(vehicle_id, Decimal("0")).quantize(Decimal("0.01")))
            if budget:
                item["monthly_budget"] = str(budget.monthly_budget) if budget.monthly_budget is not None else None
                item["trip_budget"] = str(budget.trip_budget) if budget.trip_budget is not None else None
                item["expected_efficiency_km_per_litre"] = str(budget.expected_efficiency_km_per_litre) if budget.expected_efficiency_km_per_litre is not None else None
                item["monthly_budget_exceeded"] = bool(budget.monthly_budget is not None and monthly_spend.get(vehicle_id, Decimal("0")) > budget.monthly_budget)
            item["spend"] = str(item["spend"].quantize(Decimal("0.01")))
            item["litres"] = str(item["litres"].quantize(Decimal("0.01")))
        current_month = timezone.localdate().replace(day=1)
        previous_month = month_start_with_offset(current_month, -1)
        trend_start = month_start_with_offset(current_month, -5)
        trend_rows = TripExpenseLine.objects.filter(tenant=tenant, category=TripExpenseLine.Category.FUEL,
            status=TripExpenseLine.ReviewStatus.APPROVED, is_estimated=False, incurred_at__gte=trend_start,
            incurred_at__lte=timezone.localdate()).annotate(month=TruncMonth("incurred_at")).values(
                "month", "trip__vehicle_id").annotate(spend=Sum("amount"),
                    litres=Sum("quantity_litres", filter=Q(is_refund=False)))
        months = []
        spend_by_vehicle_month = {}
        for row in trend_rows:
            month = row["month"].date().replace(day=1) if hasattr(row["month"], "date") else row["month"].replace(day=1)
            key = (str(row["trip__vehicle_id"]), month)
            spend_by_vehicle_month[key] = (row["spend"] or Decimal("0"), row["litres"] or Decimal("0"))
        for offset in range(-5, 1):
            month = month_start_with_offset(current_month, offset)
            next_month = month_start_with_offset(month, 1)
            monthly_spend_total = sum((value[0] for (vehicle_id, key_month), value in spend_by_vehicle_month.items() if key_month == month), Decimal("0"))
            monthly_litres_total = sum((value[1] for (vehicle_id, key_month), value in spend_by_vehicle_month.items() if key_month == month), Decimal("0"))
            months.append({"month": month.isoformat()[:7], "spend": str(monthly_spend_total.quantize(Decimal("0.01"))),
                "litres": str(monthly_litres_total.quantize(Decimal("0.01"))),
                "average_price_per_litre": str((monthly_spend_total/monthly_litres_total).quantize(Decimal("0.01"))) if monthly_litres_total > 0 else None,
                "days_counted": min((timezone.localdate().day if month == current_month else (next_month-month).days), (next_month-month).days),
                "is_partial": month == current_month})
        current_days = timezone.localdate().day
        previous_days = (current_month - previous_month).days
        current_spend_all = sum((value[0] for (vehicle_id, month), value in spend_by_vehicle_month.items() if month == current_month), Decimal("0"))
        previous_spend_all = sum((value[0] for (vehicle_id, month), value in spend_by_vehicle_month.items() if month == previous_month), Decimal("0"))
        overall_direction, overall_change = spend_direction(current_spend_all/current_days if current_days else Decimal("0"),
            previous_spend_all/previous_days if previous_days else Decimal("0"))
        for vehicle_id, item in vehicle_totals.items():
            cur = spend_by_vehicle_month.get((vehicle_id, current_month), (Decimal("0"), Decimal("0")))[0] / current_days
            prev = spend_by_vehicle_month.get((vehicle_id, previous_month), (Decimal("0"), Decimal("0")))[0] / previous_days
            direction, change = spend_direction(cur, prev)
            item["spend_trend"] = direction
            item["daily_spend_change_percent"] = change
            item["current_month_daily_spend"] = str(cur.quantize(Decimal("0.01")))
            item["previous_month_daily_spend"] = str(prev.quantize(Decimal("0.01")))
        if request.query_params.get("export") == "csv":
            stream = io.StringIO(newline="")
            writer = csv.writer(stream)
            writer.writerow(["Date", "Vehicle", "Trip", "Driver", "Station", "Litres", "Amount INR", "Unit price INR/L", "Fill type", "Odometer km", "Reference", "Status", "Refund"])
            for line in lines:
                litres = line.quantity_litres
                writer.writerow([line.incurred_at or "", line.trip.vehicle.registration_number, line.trip.trip_number,
                    line.trip.driver.name if line.trip.driver_id else "", line.payee, litres or "", line.amount,
                    (line.amount / litres).quantize(Decimal("0.01")) if litres else "", line.fuel_fill_type,
                    line.odometer_km or "", line.payment_reference, line.status, "Yes" if getattr(line, "is_refund", False) else "No"])
            response = HttpResponse(stream.getvalue(), content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = f'attachment; filename="fuel-report-{start}-{end}.csv"'
            return response
        trips = FleetTrip.objects.filter(tenant=tenant, status__in=[FleetTrip.Status.DRAFT, FleetTrip.Status.IN_PROGRESS,
            FleetTrip.Status.COMPLETED, FleetTrip.Status.REJECTED]).select_related("vehicle", "driver").order_by("-starts_at")[:500]
        load_state_trips = FleetTrip.objects.filter(tenant=tenant, status__in=[FleetTrip.Status.COMPLETED,
            FleetTrip.Status.SUBMITTED, FleetTrip.Status.APPROVED], odometer_start__isnull=False, odometer_end__isnull=False
            ).select_related("vehicle", "driver").order_by("-delivery_at")[:1000]
        vehicles = FleetVehicle.objects.filter(tenant=tenant).order_by("registration_number")
        budgets = FleetFuelBudget.objects.filter(tenant=tenant).select_related("vehicle")
        data = [{"id": str(line.id), "trip_id": str(line.trip_id), "trip_number": line.trip.trip_number,
            "vehicle_id": str(line.trip.vehicle_id), "vehicle": line.trip.vehicle.registration_number,
            "driver": line.trip.driver.name if line.trip.driver_id else "", "date": line.incurred_at.isoformat() if line.incurred_at else None,
            "station": line.payee, "amount": str(line.amount), "litres": str(line.quantity_litres) if line.quantity_litres is not None else None,
            "unit_price": str((line.amount / line.quantity_litres).quantize(Decimal("0.01"))) if line.quantity_litres else None,
            "fill_type": line.fuel_fill_type, "odometer_km": str(line.odometer_km) if line.odometer_km is not None else None,
            "reference": line.payment_reference, "status": line.status, "is_refund": bool(getattr(line, "is_refund", False))} for line in lines]
        totals = {"spend": str(sum((Decimal(row["amount"]) for row in data if row["status"] == "APPROVED"), Decimal("0")).quantize(Decimal("0.01"))),
            "litres": str(sum((Decimal(row["litres"] or "0") for row in data if row["status"] == "APPROVED" and not row["is_refund"]), Decimal("0")).quantize(Decimal("0.01"))),
            "entries": len(data), "pending_review": sum(1 for row in data if row["status"] in {"DRAFT", "SUBMITTED"})}
        return Response({"from": start.isoformat(), "to": end.isoformat(), "totals": totals, "by_vehicle": list(vehicle_totals.values()),
            "monthly_trends": months, "spend_trend": {"direction": overall_direction, "daily_change_percent": overall_change,
                "current_month_daily_spend": str((current_spend_all/current_days).quantize(Decimal("0.01"))) if current_days else "0.00",
                "previous_month_daily_spend": str((previous_spend_all/previous_days).quantize(Decimal("0.01"))) if previous_days else "0.00"},
            "load_state_consumption": fuel_load_state_summary(tenant, min(start, trend_start), end),
            "entries": data, "vehicles": [{"id": str(row.id), "registration_number": row.registration_number} for row in vehicles],
            "trips": [{"id": str(row.id), "trip_number": row.trip_number, "vehicle_id": str(row.vehicle_id),
                "vehicle": row.vehicle.registration_number, "driver": row.driver.name if row.driver_id else "", "status": row.status,
                "load_state": row.load_state}
                for row in trips], "budgets": [{"vehicle_id": str(row.vehicle_id), "registration_number": row.vehicle.registration_number,
                "monthly_budget": str(row.monthly_budget) if row.monthly_budget is not None else "",
                "trip_budget": str(row.trip_budget) if row.trip_budget is not None else "",
                "expected_efficiency_km_per_litre": str(row.expected_efficiency_km_per_litre) if row.expected_efficiency_km_per_litre is not None else ""} for row in budgets],
            "load_state_trips": [{"id": str(row.id), "trip_number": row.trip_number, "vehicle_id": str(row.vehicle_id),
                "vehicle": row.vehicle.registration_number, "load_state": row.load_state, "status": row.status,
                "odometer_start": str(row.odometer_start), "odometer_end": str(row.odometer_end)} for row in load_state_trips]})

    @transaction.atomic
    def post(self, request):
        from .serializers import TripExpenseLineSerializer
        if not self.access(request, write=True):
            return Response({"error": "Fuel entry permission required."}, status=403)
        trip = FleetTrip.objects.select_for_update().filter(tenant=request.tenant, id=request.data.get("trip_id")).select_related("vehicle").first()
        if not trip:
            return Response({"error": "Choose a trip in this workspace."}, status=400)
        if trip.status not in (FleetTrip.Status.DRAFT, FleetTrip.Status.IN_PROGRESS, FleetTrip.Status.COMPLETED, FleetTrip.Status.REJECTED):
            return Response({"error": "This trip has been submitted or approved; use a reviewed adjustment workflow."}, status=409)
        payload = {key: value for key, value in request.data.items() if key in {"description", "amount", "quantity_litres", "fuel_fill_type", "odometer_km", "incurred_at", "payee", "payment_reference", "idempotency_key", "receipt_id"}}
        payload.update({"category": TripExpenseLine.Category.FUEL, "status": TripExpenseLine.ReviewStatus.DRAFT})
        serializer = TripExpenseLineSerializer(data=payload, context={"tenant": request.tenant})
        serializer.is_valid(raise_exception=True)
        reference = str(serializer.validated_data.get("payment_reference", "")).strip()
        if reference and TripExpenseLine.objects.filter(tenant=request.tenant, category="FUEL", payment_reference__iexact=reference).exists():
            return Response({"error": "This receipt or transaction reference is already recorded."}, status=409)
        line = serializer.save(tenant=request.tenant, trip=trip, created_by=request.user)
        audit(request, "FLEET_FUEL_QUICK_ENTRY_CREATED", line, {"trip_id": str(trip.id), "vehicle_id": str(trip.vehicle_id), "amount": str(line.amount), "status": line.status})
        return Response({"id": str(line.id), "status": line.status, "amount": str(line.amount), "unit_price": str((line.amount / line.quantity_litres).quantize(Decimal("0.01"))) if line.quantity_litres else None}, status=201)

    @transaction.atomic
    def patch(self, request):
        if not self.access(request, write=True):
            return Response({"error": "Trip load-state edit permission required."}, status=403)
        if set(request.data) != {"trip_id", "load_state", "reason"}:
            return Response({"error": "Choose a trip load state and provide a reason for the audit history."}, status=400)
        trip = FleetTrip.objects.select_for_update().filter(tenant=request.tenant, id=request.data.get("trip_id")).first()
        if not trip:
            return Response({"error": "Trip not found in this workspace."}, status=404)
        state = request.data.get("load_state")
        reason = str(request.data.get("reason", "")).strip()
        if state not in FleetTrip.LoadState.values:
            return Response({"error": "Choose LOADED, EMPTY, or UNKNOWN."}, status=400)
        if len(reason) < 8 or len(reason) > 500:
            return Response({"error": "Enter a reason between 8 and 500 characters."}, status=400)
        previous = trip.load_state
        trip.load_state = state
        trip.save(update_fields=["load_state", "updated_at"])
        audit(request, "FLEET_TRIP_LOAD_STATE_UPDATED", trip, {"previous": previous, "load_state": state, "reason": reason,
            "historical_analysis_may_change": True})
        return Response({"id": str(trip.id), "load_state": trip.load_state, "previous_load_state": previous})

    @transaction.atomic
    def put(self, request):
        if not self.access(request, write=True):
            return Response({"error": "Fuel budget permission required."}, status=403)
        vehicle = FleetVehicle.objects.filter(tenant=request.tenant, id=request.data.get("vehicle_id")).first()
        if not vehicle:
            return Response({"error": "Choose a vehicle in this workspace."}, status=400)
        def optional_decimal(key, maximum):
            value = request.data.get(key)
            if value in (None, ""):
                return None
            try:
                parsed = Decimal(str(value))
                if not parsed.is_finite() or parsed <= 0 or parsed > maximum:
                    raise ValueError
                return parsed
            except Exception:
                raise ValueError(key)
        try:
            monthly = optional_decimal("monthly_budget", Decimal("999999999999.99"))
            trip_budget = optional_decimal("trip_budget", Decimal("999999999999.99"))
            efficiency = optional_decimal("expected_efficiency_km_per_litre", Decimal("999999.99"))
        except ValueError as exc:
            return Response({"error": f"{exc.args[0]} must be a positive number or blank."}, status=400)
        if monthly is None and trip_budget is None and efficiency is None:
            FleetFuelBudget.objects.filter(tenant=request.tenant, vehicle=vehicle).delete()
            audit(request, "FLEET_FUEL_BUDGET_REMOVED", vehicle, {"vehicle_id": str(vehicle.id)})
            return Response({"vehicle_id": str(vehicle.id), "removed": True})
        budget, _ = FleetFuelBudget.objects.update_or_create(tenant=request.tenant, vehicle=vehicle,
            defaults={"monthly_budget": monthly, "trip_budget": trip_budget, "expected_efficiency_km_per_litre": efficiency, "updated_by": request.user})
        audit(request, "FLEET_FUEL_BUDGET_UPDATED", budget, {"monthly_budget": str(monthly) if monthly is not None else None,
            "trip_budget": str(trip_budget) if trip_budget is not None else None,
            "expected_efficiency_km_per_litre": str(efficiency) if efficiency is not None else None})
        return Response({"vehicle_id": str(vehicle.id), "monthly_budget": str(monthly) if monthly is not None else "",
            "trip_budget": str(trip_budget) if trip_budget is not None else "",
            "expected_efficiency_km_per_litre": str(efficiency) if efficiency is not None else ""})


def fuel_interval_summary(lines, limit=10):
    """Calculate full-to-full km/L only when every fill in the interval is known."""
    rows = sorted(lines, key=lambda row: (row.incurred_at or timezone.localdate(), row.created_at, str(row.id)))
    undated = sum(1 for row in rows if row.incurred_at is None)
    intervals, previous_full, segment, pending_unknown = [], None, [], False
    for row in rows:
        if row.incurred_at is None:
            pending_unknown = True
            continue
        if row.fuel_fill_type == TripExpenseLine.FuelFillType.FULL:
            if previous_full is not None:
                delta_km = row.odometer_km - previous_full.odometer_km if row.odometer_km is not None and previous_full.odometer_km is not None else None
                fills = segment + [row]
                complete = not pending_unknown and all(item.fuel_fill_type in {
                    TripExpenseLine.FuelFillType.FULL, TripExpenseLine.FuelFillType.PARTIAL
                } and item.quantity_litres is not None for item in fills)
                litres = sum((item.quantity_litres or Decimal("0") for item in fills), Decimal("0"))
                fuel_cost = sum((item.amount for item in fills), Decimal("0"))
                valid = complete and delta_km is not None and delta_km > 0 and litres > 0
                intervals.append({"from_date": previous_full.incurred_at.isoformat(), "to_date": row.incurred_at.isoformat(),
                    "distance_km": str(delta_km) if delta_km is not None and delta_km > 0 else None,
                    "from_odometer_km": str(previous_full.odometer_km) if previous_full.odometer_km is not None else None,
                    "to_odometer_km": str(row.odometer_km) if row.odometer_km is not None else None,
                    "fuel_litres": str(litres) if complete else None,
                    "fuel_cost": str(fuel_cost.quantize(Decimal("0.01"))) if complete else None,
                    "efficiency_km_per_litre": str((delta_km / litres).quantize(Decimal("0.01"))) if valid else None,
                    "status": "CALCULATED" if valid else "REVIEW_REQUIRED"})
            previous_full = row if row.odometer_km is not None else None
            segment, pending_unknown = [], row.odometer_km is None
        elif previous_full is not None:
            segment.append(row)
            if row.fuel_fill_type != TripExpenseLine.FuelFillType.PARTIAL or row.quantity_litres is None:
                pending_unknown = True
    calculated = [row for row in intervals if row["status"] == "CALCULATED"]
    latest = calculated[-1] if calculated else None
    return {"fill_record_count": len(rows), "undated_fill_count": undated,
        "interval_count": len(intervals), "latest_efficiency_km_per_litre": latest["efficiency_km_per_litre"] if latest else None,
        "status": "REVIEW_REQUIRED" if any(row["status"] == "REVIEW_REQUIRED" for row in intervals) or undated else "CALCULATED" if latest else "INSUFFICIENT_DATA",
        "intervals": intervals[-limit:] if limit else intervals,
        "basis": "Approved actual fuel expenses between consecutive recorded full fills, using fill odometers. Partial or unknown fills and missing readings do not produce an efficiency value."}


def fuel_load_state_summary(tenant, start, end):
    """Attribute measured full-to-full fuel intervals only when trip odometers cover the whole interval in one known load state."""
    from datetime import date as date_type, datetime as datetime_type, time as time_type
    from .models import FleetTrip
    fills_by_vehicle = {}
    for row in TripExpenseLine.objects.filter(tenant=tenant, category=TripExpenseLine.Category.FUEL,
            status=TripExpenseLine.ReviewStatus.APPROVED, is_estimated=False, is_refund=False,
            incurred_at__isnull=False, incurred_at__lte=end).select_related("trip").order_by("trip__vehicle_id", "incurred_at", "created_at"):
        fills_by_vehicle.setdefault(row.trip.vehicle_id, []).append(row)
    trips_by_vehicle = {}
    trips = FleetTrip.objects.filter(tenant=tenant, vehicle_id__in=fills_by_vehicle,
        status__in=[FleetTrip.Status.COMPLETED, FleetTrip.Status.SUBMITTED, FleetTrip.Status.APPROVED],
        odometer_start__isnull=False, odometer_end__isnull=False).select_related("vehicle").order_by("vehicle_id", "odometer_start")
    for trip in trips:
        trips_by_vehicle.setdefault(trip.vehicle_id, []).append(trip)
    result = {state: {"intervals": 0, "distance_km": Decimal("0"), "fuel_litres": Decimal("0"),
        "fuel_cost": Decimal("0"), "trips": set(), "evidence": []} for state in ("EMPTY", "LOADED")}
    unclassified = {"insufficient_trip_odometer_coverage": 0, "unknown_or_mixed_load_state": 0}
    for vehicle_id, fills in fills_by_vehicle.items():
        intervals = fuel_interval_summary(fills, limit=None)["intervals"]
        for interval in intervals:
            if interval["status"] != "CALCULATED" or not (start.isoformat() <= interval["to_date"] <= end.isoformat()):
                continue
            lo, hi = Decimal(interval["from_odometer_km"] or "0"), Decimal(interval["to_odometer_km"] or "0")
            distance = Decimal(interval["distance_km"] or "0")
            if hi <= lo or distance <= 0:
                unclassified["insufficient_trip_odometer_coverage"] += 1
                continue
            interval_start = datetime.combine(date_type.fromisoformat(interval["from_date"]), time_type.min).replace(tzinfo=timezone.get_current_timezone())
            interval_end = datetime.combine(date_type.fromisoformat(interval["to_date"]), time_type.max).replace(tzinfo=timezone.get_current_timezone())
            spans = []
            for trip in trips_by_vehicle.get(vehicle_id, []):
                trip_start, trip_end = trip.starts_at or trip.pickup_at, trip.delivery_at or trip.ends_at
                if not trip_start or not trip_end or trip_end < interval_start or trip_start > interval_end:
                    continue
                t0, t1 = trip.odometer_start, trip.odometer_end
                if t1 <= lo or t0 >= hi:
                    continue
                a, b = max(t0, lo), min(t1, hi)
                if b > a:
                    spans.append((a, b, trip))
            spans.sort(key=lambda part: (part[0], part[1], str(part[2].id)))
            cursor, covered, states, labels, valid_coverage = lo, Decimal("0"), set(), [], True
            for a, b, trip in spans:
                if a < cursor - Decimal("2") or a > cursor + Decimal("5"):
                    valid_coverage = False
                    break
                covered += b - max(cursor, a)
                cursor = max(cursor, b)
                states.add(trip.load_state)
                labels.append(trip.trip_number)
            tolerance = max(Decimal("5"), distance * Decimal("0.02"))
            if not valid_coverage or abs(covered-distance) > tolerance or abs(cursor-hi) > tolerance:
                unclassified["insufficient_trip_odometer_coverage"] += 1
                continue
            if len(states) != 1 or not states.issubset({FleetTrip.LoadState.EMPTY, FleetTrip.LoadState.LOADED}):
                unclassified["unknown_or_mixed_load_state"] += 1
                continue
            state = next(iter(states))
            item = result[state]
            litres, cost = Decimal(interval["fuel_litres"]), Decimal(interval["fuel_cost"] or "0")
            item["intervals"] += 1
            item["distance_km"] += distance
            item["fuel_litres"] += litres
            item["fuel_cost"] += cost
            item["trips"].update(labels)
            item["evidence"].append({"from_date": interval["from_date"], "to_date": interval["to_date"],
                "trip_numbers": labels, "distance_km": str(distance), "fuel_litres": str(litres),
                "fuel_cost": str(cost.quantize(Decimal("0.01"))), "load_state": state})
    for state, item in result.items():
        km, litres = item["distance_km"], item["fuel_litres"]
        item["efficiency_km_per_litre"] = str((km/litres).quantize(Decimal("0.01"))) if km > 0 and litres > 0 else None
        item["cost_per_km"] = str((item["fuel_cost"]/km).quantize(Decimal("0.01"))) if km > 0 else None
        item["distance_km"] = str(km.quantize(Decimal("0.1")))
        item["fuel_litres"] = str(litres.quantize(Decimal("0.01")))
        item["fuel_cost"] = str(item["fuel_cost"].quantize(Decimal("0.01")))
        item["trip_count"] = len(item["trips"])
        del item["trips"]
    return {"empty": result["EMPTY"], "loaded": result["LOADED"], "unclassified_interval_count": sum(unclassified.values()),
        "unclassified_reasons": unclassified,
        "basis": "Measured only from approved full-to-full fuel intervals whose trip odometers cover the interval and whose trips all have the same explicit load state. Mixed, unknown, or incomplete intervals are excluded."}


class DockDetentionAction(APIView):
    permission_classes = [HasTenantMembership]

    @transaction.atomic
    def post(self, request, appointment_id, action):
        if request.membership.role not in EDIT_ROLES | REVIEW_ROLES:
            return Response({"error": "Fleet edit access required."}, status=403)
        row = DockAppointment.objects.select_for_update(of=("self",)).select_related("tenant", "dock", "order__customer").filter(tenant=request.tenant, id=appointment_id).first()
        if not row: return Response({"error": "Appointment not found."}, status=404)
        note = str(request.data.get("reason", "")).strip()[:500]
        if action == "finish-loading":
            if row.status != "LOADING" or row.loading_finished_at:
                return Response({"error": "Loading is not active or its finish time is already recorded."}, status=409)
            row.loading_finished_at = timezone.now()
        elif action == "reason":
            if not note: return Response({"error": "A delay reason is required."}, status=400)
            row.delay_reason = note
        elif action == "prepare-billing":
            if row.detention_revenue_id:
                return Response(dock_appointment_data(row))
            if row.status != "COMPLETED" or row.rate_snapshot is None or not row.checked_out_at:
                return Response({"error": "Complete a checked-in appointment with a recorded contract rate first."}, status=409)
            trip = FleetTrip.objects.select_for_update().filter(tenant=request.tenant, transport_order=row.order).first()
            if not trip or trip.status not in {"DRAFT", "IN_PROGRESS", "COMPLETED", "REJECTED"} or TransportInvoice.objects.filter(tenant=request.tenant, order=row.order).exists():
                return Response({"error": "Detention must be prepared on an editable trip before approval and customer invoicing."}, status=409)
            amount = Decimal(dock_appointment_data(row)["detention_estimate"])
            if amount <= 0 or not (row.delay_reason or note):
                return Response({"error": "A positive charge estimate and delay reason are required."}, status=400)
            row.delay_reason = note or row.delay_reason
            row.detention_revenue = TripRevenueLine.objects.create(tenant=request.tenant, trip=trip,
                description=f"Detention at {row.dock.name}"[:160], amount=amount, is_estimated=False, status="DRAFT")
        else: return Response({"error": "Unknown detention action."}, status=404)
        row.save()
        audit(request, f"DOCK_{action.upper().replace('-', '_')}", row, {"reason": note,
            "detention_revenue_id": str(row.detention_revenue_id) if row.detention_revenue_id else None})
        return Response(dock_appointment_data(row))


class MaintenanceReliability(APIView):
    permission_classes = [HasTenantMembership]

    def get(self, request):
        if request.membership.role not in EDIT_ROLES | REVIEW_ROLES:
            return Response({"error": "Fleet operations access required."}, status=403)
        output = []
        trip_states = [FleetTrip.Status.COMPLETED, FleetTrip.Status.SUBMITTED, FleetTrip.Status.APPROVED]
        vehicles = FleetVehicle.objects.filter(tenant=request.tenant).prefetch_related("maintenance_records").annotate(
            first_km=Min("trips__odometer_start", filter=Q(trips__status__in=trip_states)),
            last_km=Max("trips__odometer_end", filter=Q(trips__status__in=trip_states)))
        fuel_by_vehicle = {}
        fuel_lines = TripExpenseLine.objects.filter(tenant=request.tenant, category=TripExpenseLine.Category.FUEL,
            status=TripExpenseLine.ReviewStatus.APPROVED, is_estimated=False, is_refund=False).select_related("trip").order_by("trip__vehicle_id", "incurred_at", "created_at")
        for line in fuel_lines:
            fuel_by_vehicle.setdefault(line.trip.vehicle_id, []).append(line)
        now = timezone.now()
        for truck in vehicles:
            records = list(truck.maintenance_records.all())
            spend = sum((r.cost for r in records), Decimal("0"))
            events = [(r.breakdown_at, r.returned_to_service_at or now) for r in records if r.breakdown_at]
            # Merge overlapping repair intervals so downtime is not counted twice.
            merged = []
            for start, end in sorted(events):
                if merged and start <= merged[-1][1]: merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
                else: merged.append((start, end))
            downtime = sum((end-start).total_seconds() for start,end in merged)/3600
            odometer_events = []
            for trip in truck.trips.filter(status__in=trip_states).exclude(odometer_start__isnull=True, odometer_end__isnull=True):
                start_at = trip.pickup_at or trip.starts_at or trip.created_at
                end_at = trip.delivery_at or trip.ends_at or trip.updated_at
                if trip.odometer_start is not None:
                    odometer_events.append((start_at, trip.odometer_start, f"Trip {trip.trip_number} start"))
                if trip.odometer_end is not None:
                    odometer_events.append((end_at, trip.odometer_end, f"Trip {trip.trip_number} end"))
            for record in records:
                if record.odometer_km is not None:
                    service_at = timezone.make_aware(datetime.combine(record.service_date, time.min))
                    odometer_events.append((service_at, record.odometer_km, f"Maintenance {record.get_category_display()} ({record.service_date.isoformat()})"))
            odometer_events.sort(key=lambda event: (event[0],
                0 if event[2].endswith(" start") else 2 if event[2].endswith(" end") else 1, event[2]))
            odometer_issues = []
            previous = None
            for event_at, reading, label in odometer_events:
                same_day_maintenance_order = previous and event_at.date() == previous[0].date() and (
                    event_at.time() == time.min or previous[0].time() == time.min)
                if previous and reading < previous[1] and not same_day_maintenance_order:
                    odometer_issues.append({"at": event_at.isoformat(), "reading_km": str(reading),
                        "evidence": label, "previous_reading_km": str(previous[1]),
                        "previous_evidence": previous[2],
                        "message": "Recorded odometer decreased. Check the source reading, event date, or vehicle assignment."})
                if previous is None or event_at >= previous[0]:
                    previous = (event_at, reading, label)
            distance = (truck.last_km - truck.first_km if not odometer_issues and
                truck.last_km is not None and truck.first_km is not None else None)
            failures = {}
            for record in records:
                if record.failure_code: failures[record.failure_code] = failures.get(record.failure_code, 0) + 1
            reasons = []
            latest = {}
            for record in sorted(records,key=lambda r:(r.service_date,r.created_at),reverse=True):latest.setdefault(record.category,record)
            latest_service_records = list(latest.values())
            if any(r.breakdown_at and not r.returned_to_service_at for r in records): reasons.append("Truck has an open breakdown.")
            if any(r.next_due_date and r.next_due_date <= now.date() for r in latest_service_records): reasons.append("A recorded service date is due.")
            if any(r.next_due_odometer_km is not None and truck.last_km is not None and r.next_due_odometer_km <= truck.last_km for r in latest_service_records): reasons.append("A recorded odometer service threshold is due.")
            if odometer_issues: reasons.append("Recorded odometer readings are out of sequence; review before using distance or cost-per-kilometre figures.")
            if any(count >= 2 for count in failures.values()): reasons.append("A failure code was recorded more than once; inspect repair history.")
            output.append({"vehicle_id": str(truck.id), "registration_number": truck.registration_number,
                "vehicle_type":truck.vehicle_type,"capacity_unit":truck.capacity_unit,"capacity":str(truck.capacity) if truck.capacity is not None else None,
                "maintenance_cost": str(spend), "recorded_distance_km": str(distance) if distance is not None else None,
                "cost_per_km": str((spend/distance).quantize(Decimal("0.01"))) if distance and distance > 0 else None,
                "fuel_efficiency": fuel_interval_summary(fuel_by_vehicle.get(truck.id, [])),
                "odometer_integrity": {"status": "REVIEW_REQUIRED" if odometer_issues else "CONSISTENT" if odometer_events else "INSUFFICIENT_DATA",
                    "event_count": len(odometer_events), "latest_reading_km": str(odometer_events[-1][1]) if odometer_events else None,
                    "issues": odometer_issues[:20]},
                "downtime_hours": round(downtime,2), "failure_counts": failures, "assignment_risk_reasons": reasons,
                "basis": "All recorded maintenance costs divided by recorded odometer span; incomplete records may distort this metric."})
        return Response({"vehicles": output})


class MaintenanceReturnToService(APIView):
    permission_classes = [HasTenantMembership]
    @transaction.atomic
    def post(self, request, record_id):
        if request.membership.role not in EDIT_ROLES:
            return Response({"error": "Fleet edit access required."}, status=403)
        row = FleetMaintenanceRecord.objects.select_for_update().filter(tenant=request.tenant, id=record_id).first()
        reason = str(request.data.get("reason", "")).strip()[:500]
        if not row: return Response({"error": "Maintenance record not found."}, status=404)
        if not row.breakdown_at or row.returned_to_service_at or not reason:
            return Response({"error": "Choose an open breakdown and record a return-to-service reason."}, status=409)
        row.returned_to_service_at = timezone.now()
        row.save(update_fields=["returned_to_service_at"])
        audit(request, "TRUCK_RETURNED_TO_SERVICE", row, {"reason": reason})
        return Response({"returned_to_service_at": row.returned_to_service_at.isoformat()})


class ReturnLoadHistory(APIView):
    permission_classes = [HasTenantMembership]
    def get(self, request):
        if request.membership.role not in EDIT_ROLES | REVIEW_ROLES:
            return Response({"error": "Fleet dispatch access required."}, status=403)
        rows = ReturnLoadOffer.objects.filter(tenant=request.tenant).select_related("source_trip__vehicle", "order__customer", "trip", "offered_by", "accepted_by").order_by("-updated_at")[:500]
        return Response([{"id":str(r.id),"status":r.status,"order":r.order.order_number,"customer":r.order.customer.name,
            "truck":r.source_trip.vehicle.registration_number,"proposed_amount":str(r.proposed_amount),
            "accepted_amount":str(r.accepted_amount) if r.accepted_amount is not None else None,
            "trip":r.trip.trip_number if r.trip_id else None,"notes":r.notes,"updated_at":r.updated_at.isoformat()} for r in rows])


class ReturnLoadCancel(APIView):
    permission_classes = [HasTenantMembership]
    @transaction.atomic
    def post(self, request, offer_id):
        if request.membership.role not in EDIT_ROLES:
            return Response({"error": "Fleet edit access required."}, status=403)
        row = ReturnLoadOffer.objects.filter(tenant=request.tenant, id=offer_id).first()
        reason = str(request.data.get("reason", "")).strip()[:500]
        if not row: return Response({"error": "Booking not found."}, status=404)
        if row.status != "BOOKED" or not row.trip_id or not reason:
            return Response({"error": "Only a booked return load can be cancelled, with a reason."}, status=409)
        from .models import TransportOrder
        order = TransportOrder.objects.select_for_update().get(tenant=request.tenant, id=row.order_id)
        row = ReturnLoadOffer.objects.select_for_update().get(tenant=request.tenant,id=offer_id)
        if row.status != "BOOKED" or not row.trip_id:
            return Response({"error":"This booking changed. Refresh its history."},status=409)
        trip = FleetTrip.objects.select_for_update().get(tenant=request.tenant, id=row.trip_id)
        if trip.status != "DRAFT" or trip.pickup_at or trip.revenue_lines.exists() or trip.expense_lines.exists() or TransportInvoice.objects.filter(tenant=request.tenant, trip=trip).exists():
            return Response({"error": "Only an unstarted trip without financial records can be cancelled here. Review active-trip changes with operations."}, status=409)
        trip.status, trip.transport_order = "CANCELLED", None
        trip.save(update_fields=["status", "transport_order", "updated_at"])
        from .models import FleetResourceReservation
        FleetResourceReservation.objects.filter(tenant=request.tenant, trip=trip, released_at__isnull=True).update(released_at=timezone.now())
        order.status = "OPEN"
        order.save(update_fields=["status", "updated_at"])
        row.status = "CANCELLED"
        row.save(update_fields=["status", "updated_at"])
        audit(request, "RETURN_LOAD_CANCELLED", row, {"reason":reason,"order_id":str(order.id),"trip_id":str(trip.id)})
        return Response({"status":row.status})
