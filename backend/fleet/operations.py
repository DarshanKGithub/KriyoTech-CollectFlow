from decimal import Decimal
from django.db import transaction
from django.db.models import Sum, Min, Max
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView
from accounts.permissions import HasTenantMembership
from .models import DockAppointment, FleetMaintenanceRecord, FleetTrip, FleetVehicle, ReturnLoadOffer, TransportInvoice, TripRevenueLine
from .views import EDIT_ROLES, REVIEW_ROLES, audit, dock_appointment_data


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
        vehicles = FleetVehicle.objects.filter(tenant=request.tenant).prefetch_related("maintenance_records").annotate(
            first_km=Min("trips__odometer_start"), last_km=Max("trips__odometer_end"))
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
            distance = truck.last_km - truck.first_km if truck.last_km is not None and truck.first_km is not None else None
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
            if any(count >= 2 for count in failures.values()): reasons.append("A failure code was recorded more than once; inspect repair history.")
            output.append({"vehicle_id": str(truck.id), "registration_number": truck.registration_number,
                "vehicle_type":truck.vehicle_type,"capacity_unit":truck.capacity_unit,"capacity":str(truck.capacity) if truck.capacity is not None else None,
                "maintenance_cost": str(spend), "recorded_distance_km": str(distance) if distance is not None else None,
                "cost_per_km": str((spend/distance).quantize(Decimal("0.01"))) if distance and distance > 0 else None,
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
        order.status = "OPEN"
        order.save(update_fields=["status", "updated_at"])
        row.status = "CANCELLED"
        row.save(update_fields=["status", "updated_at"])
        audit(request, "RETURN_LOAD_CANCELLED", row, {"reason":reason,"order_id":str(order.id),"trip_id":str(trip.id)})
        return Response({"status":row.status})
