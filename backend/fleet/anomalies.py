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
