from decimal import Decimal
from statistics import median
from django.db.models import Prefetch
from .models import FleetTrip,TripExpenseLine
from .compatibility import canonical_unit


def contextual_fuel_alerts(tenant):
    from .views import normalize_location
    fuel=TripExpenseLine.objects.filter(tenant=tenant,category="FUEL",status="APPROVED",is_estimated=False)
    trips=FleetTrip.objects.filter(tenant=tenant,status__in=["COMPLETED","SUBMITTED","APPROVED"],delivery_at__isnull=False,
        odometer_start__isnull=False,odometer_end__isnull=False,transport_order__isnull=False).select_related("vehicle","transport_order").prefetch_related(Prefetch("expense_lines",queryset=fuel,to_attr="_fuel_evidence")).order_by("-delivery_at")[:1500]
    records=[]
    for trip in trips:
        distance=trip.odometer_end-trip.odometer_start
        litres=sum((line.quantity_litres or Decimal("0") for line in trip._fuel_evidence),Decimal("0"))
        order=trip.transport_order;unit=canonical_unit(order.load_unit)
        if distance<=0 or litres<=0 or order.load_quantity is None or order.load_quantity<=0 or unit not in {"TONNE","KG"}:continue
        load_kg=order.load_quantity*(1000 if unit=="TONNE" else 1)
        lane=(normalize_location(trip.origin or order.origin),normalize_location(trip.destination or order.destination))
        if not all(lane):continue
        records.append({"trip":trip,"lane":lane,"load":load_kg,"distance":distance,"litres":litres,"rate":litres/distance})
    alerts=[]
    tolerance=Decimal(str(tenant.settings.get("fleet_controls",{}).get("fuel_efficiency_tolerance_percent","20")))/100
    for current in records[:100]:
        trip=current["trip"]
        references=[r for r in records if r["trip"].vehicle_id==trip.vehicle_id and r["lane"]==current["lane"]
            and r["trip"].delivery_at<trip.delivery_at and abs(r["load"]-current["load"])/current["load"]<=Decimal("0.20")]
        if len(references)<5:continue
        baseline=median([r["rate"] for r in references])
        if current["rate"]<=baseline*(1+tolerance):continue
        variance=(current["rate"]/baseline-1)*100
        alerts.append({"id":f"context-fuel:{trip.id}","kind":"CONTEXTUAL_FUEL_ANOMALY","trip_id":str(trip.id),"trip_number":trip.trip_number,
            "message":f"Fuel litres/km is {variance:.1f}% above this truck's historical median on the same lane with loads within 20% of the recorded cargo weight.",
            "amount":str(current["litres"]),"distance_km":str(current["distance"]),"load_kg":str(current["load"]),
            "litres_per_km":str(current["rate"].quantize(Decimal("0.0001"))),"baseline_litres_per_km":str(baseline.quantize(Decimal("0.0001"))),
            "reference_sample_count":len(references),"reference_trips":[r["trip"].trip_number for r in references[:20]],
            "next_action":"Compare receipts, odometer readings, actual cargo weight and operating conditions. This signal is not a fraud finding."})
    return alerts


def full_fill_consumption_alerts(tenant):
    """Flag reviewable, evidence-backed full-to-full efficiency drops; never label them theft."""
    from statistics import median as median_value
    from .operations import fuel_interval_summary

    rows = TripExpenseLine.objects.filter(tenant=tenant, category=TripExpenseLine.Category.FUEL,
        status=TripExpenseLine.ReviewStatus.APPROVED, is_estimated=False, is_refund=False).select_related("trip__vehicle").order_by(
            "trip__vehicle_id", "incurred_at", "created_at")
    by_vehicle = {}
    vehicles = {}
    for row in rows:
        by_vehicle.setdefault(row.trip.vehicle_id, []).append(row)
        vehicles[row.trip.vehicle_id] = row.trip.vehicle
    try:
        tolerance = Decimal(str(tenant.settings.get("fleet_controls", {}).get("fuel_efficiency_tolerance_percent", "20"))) / 100
    except Exception:
        tolerance = Decimal("0.20")
    alerts = []
    for vehicle_id, fills in by_vehicle.items():
        intervals = fuel_interval_summary(fills)["intervals"]
        valid = [row for row in intervals if row["status"] == "CALCULATED"]
        for index in range(3, len(valid)):
            current = valid[index]
            references = valid[max(0, index - 5):index]
            if len(references) < 3:
                continue
            baseline = Decimal(str(median_value([Decimal(row["efficiency_km_per_litre"]) for row in references])))
            efficiency = Decimal(current["efficiency_km_per_litre"])
            if baseline <= 0 or efficiency >= baseline * (1 - tolerance):
                continue
            variance = (baseline - efficiency) * 100 / baseline
            vehicle = vehicles[vehicle_id]
            simulated = bool((tenant.settings or {}).get("demo_workspace"))
            prefix = "SIMULATION · " if simulated else ""
            alerts.append({"id": f"full-fill-fuel:{vehicle_id}:{current['to_date']}",
                "kind": "FULL_FILL_FUEL_CONSUMPTION_REVIEW", "vehicle_id": str(vehicle_id),
                "vehicle": vehicle.registration_number, "from_date": current["from_date"], "to_date": current["to_date"],
                "efficiency_km_per_litre": current["efficiency_km_per_litre"],
                "baseline_km_per_litre": str(baseline.quantize(Decimal("0.01"))),
                "fuel_litres": current["fuel_litres"], "distance_km": current["distance_km"],
                "reference_interval_count": len(references), "synthetic_demo": simulated,
                "message": f"{prefix}{vehicle.registration_number} recorded {efficiency:.2f} km/L, {variance:.1f}% below its recent full-fill median of {baseline:.2f} km/L.",
                "next_action": "Review the fill receipts, odometer readings, route, load and maintenance context. This is a consumption review signal, not a fuel-loss or theft finding."})
    return alerts


def fuel_budget_alerts(tenant):
    """Create explainable budget review prompts from approved, actual fuel records."""
    from django.db.models import Sum
    from django.utils import timezone
    from .models import FleetFuelBudget
    from .operations import fuel_interval_summary
    month_start = timezone.localdate().replace(day=1)
    month_end = timezone.localdate()
    alerts = []
    budgets = FleetFuelBudget.objects.filter(tenant=tenant, monthly_budget__isnull=False).select_related("vehicle")
    for budget in budgets:
        spend = TripExpenseLine.objects.filter(tenant=tenant, category=TripExpenseLine.Category.FUEL,
            status=TripExpenseLine.ReviewStatus.APPROVED, is_estimated=False, trip__vehicle_id=budget.vehicle_id,
            incurred_at__gte=month_start, incurred_at__lte=month_end).aggregate(total=Sum("amount"))["total"] or Decimal("0")
        if spend <= budget.monthly_budget:
            continue
        simulated = bool((tenant.settings or {}).get("demo_workspace"))
        prefix = "SIMULATION · " if simulated else ""
        alerts.append({"id": f"fuel-budget:{budget.vehicle_id}:{month_start.isoformat()}",
            "kind": "FUEL_MONTHLY_BUDGET_REVIEW", "vehicle_id": str(budget.vehicle_id),
            "vehicle": budget.vehicle.registration_number, "month": month_start.isoformat()[:7],
            "approved_monthly_spend": str(spend.quantize(Decimal("0.01"))), "monthly_budget": str(budget.monthly_budget),
            "over_budget_amount": str((spend - budget.monthly_budget).quantize(Decimal("0.01"))), "synthetic_demo": simulated,
            "message": f"{prefix}{budget.vehicle.registration_number} approved fuel spend is ₹{spend:.2f}, above its ₹{budget.monthly_budget:.2f} monthly budget.",
            "next_action": "Check the approved fills, route activity, budget period and any credits before changing the vehicle target."})
    all_budgets = FleetFuelBudget.objects.filter(tenant=tenant).select_related("vehicle")
    for budget in all_budgets:
        simulated = bool((tenant.settings or {}).get("demo_workspace"))
        prefix = "SIMULATION · " if simulated else ""
        if budget.trip_budget is not None:
            trip_spends = TripExpenseLine.objects.filter(tenant=tenant, category=TripExpenseLine.Category.FUEL,
                status=TripExpenseLine.ReviewStatus.APPROVED, is_estimated=False, trip__vehicle_id=budget.vehicle_id).values(
                    "trip_id", "trip__trip_number").annotate(total=Sum("amount"))
            for item in trip_spends:
                spend = item["total"] or Decimal("0")
                if spend <= budget.trip_budget:
                    continue
                alerts.append({"id": f"fuel-trip-budget:{item['trip_id']}", "kind": "FUEL_TRIP_BUDGET_REVIEW",
                    "vehicle_id": str(budget.vehicle_id), "vehicle": budget.vehicle.registration_number,
                    "trip_number": item["trip__trip_number"], "trip_fuel_spend": str(spend.quantize(Decimal("0.01"))),
                    "trip_budget": str(budget.trip_budget), "over_budget_amount": str((spend-budget.trip_budget).quantize(Decimal("0.01"))),
                    "synthetic_demo": simulated,
                    "message": f"{prefix}{budget.vehicle.registration_number} fuel expenses for trip {item['trip__trip_number']} total ₹{spend:.2f}, above the ₹{budget.trip_budget:.2f} per-trip target.",
                    "next_action": "Review the trip receipts, litres, odometer, route and any credits against the per-trip target."})
        if budget.expected_efficiency_km_per_litre is not None:
            fuel_rows = TripExpenseLine.objects.filter(tenant=tenant, category=TripExpenseLine.Category.FUEL,
                status=TripExpenseLine.ReviewStatus.APPROVED, is_estimated=False, is_refund=False,
                trip__vehicle_id=budget.vehicle_id).select_related("trip").order_by("trip__vehicle_id", "incurred_at", "created_at")
            efficiency = fuel_interval_summary(fuel_rows)
            actual = Decimal(efficiency["latest_efficiency_km_per_litre"]) if efficiency["latest_efficiency_km_per_litre"] else None
            target = budget.expected_efficiency_km_per_litre
            if actual is not None and actual < target * Decimal("0.80"):
                alerts.append({"id": f"fuel-efficiency-target:{budget.vehicle_id}:{timezone.localdate().isoformat()}",
                    "kind": "FUEL_EFFICIENCY_TARGET_REVIEW", "vehicle_id": str(budget.vehicle_id),
                    "vehicle": budget.vehicle.registration_number, "efficiency_km_per_litre": str(actual),
                    "expected_efficiency_km_per_litre": str(target), "synthetic_demo": simulated,
                    "message": f"{prefix}{budget.vehicle.registration_number} latest full-to-full efficiency is {actual} km/L, below its {target} km/L benchmark.",
                    "next_action": "Check the full-fill interval, station receipts, odometer readings, route, load and maintenance context. This comparison is a review signal, not a theft finding."})
    return alerts
