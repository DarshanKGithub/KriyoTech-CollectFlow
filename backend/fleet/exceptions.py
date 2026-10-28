"""Persistent review cases for existing evidence-based fleet signals."""
import csv
import io
import hashlib
import json
from datetime import timedelta
from uuid import UUID

from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Membership
from accounts.permissions import HasTenantMembership
from audit.models import AuditLog
from .models import FleetExceptionCase


def sync_cases(request):
    from .views import FleetAlerts, FleetRevenueLeakage, dock_appointment_data
    from .models import DockAppointment
    from .operations import MaintenanceReliability
    alerts = FleetAlerts().get(request).data.get("alerts", [])
    from .anomalies import contextual_fuel_alerts
    alerts.extend(contextual_fuel_alerts(request.tenant))
    leakage = FleetRevenueLeakage().get(request).data.get("items", [])
    for appointment in DockAppointment.objects.filter(tenant=request.tenant, status__in=["ARRIVED", "LOADING"]).select_related("tenant", "dock", "order__customer"):
        evidence = dock_appointment_data(appointment)
        if evidence["chargeable_minutes"] > 0:
            alerts.append({**evidence, "id":f"detention:{appointment.id}", "kind":"DETENTION_OVER_FREE_TIME",
                "message":f"{appointment.order.order_number} has exceeded free waiting time by {evidence['chargeable_minutes']} minutes."})
    for truck in MaintenanceReliability().get(request).data.get("vehicles", []):
        if truck["assignment_risk_reasons"]:
            alerts.append({**truck, "id":f"assignment-risk:{truck['vehicle_id']}", "kind":"TRUCK_ASSIGNMENT_RISK",
                "message":f"{truck['registration_number']}: {' '.join(truck['assignment_risk_reasons'])}"})
    count = 0
    controls = request.tenant.settings.get("fleet_controls", {})
    default_owner = Membership.objects.filter(tenant=request.tenant,is_active=True,role="FLEET").first() or Membership.objects.filter(tenant=request.tenant,is_active=True,role="OWNER").first()
    policy_version = hashlib.sha256(json.dumps(controls,sort_keys=True).encode()).hexdigest()[:16]
    deadline = timezone.now() + timedelta(hours=int(controls.get("escalation_hours", 24)))
    for prefix, rows in (("alert", alerts), ("revenue", leakage)):
        for row in rows:
            if row.get("is_open") is False:continue
            fingerprint=hashlib.sha256(json.dumps({"message":row.get("message"),"amount":row.get("amount"),"outstanding_amount":row.get("outstanding_amount"),"policy_version":policy_version},sort_keys=True).encode()).hexdigest()
            case, created = FleetExceptionCase.objects.get_or_create(tenant=request.tenant,
                source_key=f"{prefix}:{row['id']}", defaults={"category": row.get("kind", row.get("issue", "REVIEW")),
                    "evidence": {**row,"policy_version":policy_version,"source_fingerprint":fingerprint}, "due_at": deadline,"owner_id":default_owner.user_id if default_owner else None})
            if not created and case.status in {"DISMISSED","RESOLVED"} and case.evidence.get("source_fingerprint") and case.evidence["source_fingerprint"]!=fingerprint:
                with transaction.atomic():
                    locked=FleetExceptionCase.objects.select_for_update().get(id=case.id,tenant=request.tenant)
                    if locked.status in {"DISMISSED","RESOLVED"} and locked.evidence.get("source_fingerprint")!=fingerprint:
                        AuditLog.objects.create(tenant=request.tenant,action="FLEET_EXCEPTION_SOURCE_CHANGED",object_type="FleetExceptionCase",object_id=str(locked.id),
                            metadata={"previous_status":locked.status,"previous_note":locked.review_note,"previous_evidence":locked.evidence})
                        locked.status="OPEN";locked.evidence={**row,"policy_version":policy_version,"source_fingerprint":fingerprint};locked.due_at=deadline
                        locked.review_note="Source evidence or policy changed; review again.";locked.reviewed_at=None;locked.reviewed_by=None;locked.save()
            count += int(created)
    if default_owner:
        for case in FleetExceptionCase.objects.filter(tenant=request.tenant,owner__isnull=True,status__in=["OPEN","CONFIRMED"])[:500]:
            with transaction.atomic():
                locked=FleetExceptionCase.objects.select_for_update().get(tenant=request.tenant,id=case.id)
                if locked.owner_id:continue
                locked.owner_id=default_owner.user_id;locked.save(update_fields=["owner","updated_at"])
                AuditLog.objects.create(tenant=request.tenant,action="FLEET_EXCEPTION_AUTO_ASSIGNED",object_type="FleetExceptionCase",object_id=str(locked.id),metadata={"owner_id":str(default_owner.user_id),"reason":"Default fleet operator, or workspace owner when no fleet operator is configured."})
    return count


def case_data(row):
    return {"id": str(row.id), "source_key": row.source_key, "category": row.category,
        "evidence": row.evidence, "status": row.status, "owner_id": str(row.owner_id) if row.owner_id else None,
        "owner": row.owner.email if row.owner_id else None, "due_at": row.due_at.isoformat() if row.due_at else None,
        "overdue": bool(row.due_at and row.due_at < timezone.now() and row.status in {"OPEN", "CONFIRMED"}),
        "review_note": row.review_note, "reviewed_by": row.reviewed_by.email if row.reviewed_by_id else None,
        "public_resolution":row.public_resolution,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat()}


class FleetExceptions(APIView):
    permission_classes = [HasTenantMembership]

    def allowed(self, request):
        return request.membership.role in {"OWNER", "FINANCE", "FLEET", "APPROVER"}

    def get(self, request):
        if not self.allowed(request):
            return Response({"error": "Fleet review access required."}, status=403)
        rows = FleetExceptionCase.objects.filter(tenant=request.tenant).select_related("owner", "reviewed_by").order_by("status", "due_at", "-created_at")
        if request.query_params.get("status"):
            rows = rows.filter(status=request.query_params["status"])
        if request.query_params.get("export") == "csv":
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["Case", "Category", "Status", "Owner", "Due", "Evidence", "Review note"])
            for row in rows[:10000]:
                # Prevent spreadsheet formula execution from imported evidence or user notes.
                values = [str(row.id), row.category, row.status, row.owner.email if row.owner_id else "", row.due_at,
                    row.evidence.get("message", ""), row.review_note]
                writer.writerow(["'" + str(value) if str(value).lstrip().startswith(("=", "+", "-", "@")) else value for value in values])
            response = HttpResponse(output.getvalue(), content_type="text/csv")
            response["Content-Disposition"] = 'attachment; filename="fleet-exceptions.csv"'
            return response
        try:
            page=max(1,int(request.query_params.get("page",1)));page_size=min(100,max(1,int(request.query_params.get("page_size",50))))
        except (ValueError,TypeError):return Response({"error":"Enter a valid page and page size."},status=400)
        members = Membership.objects.filter(tenant=request.tenant, is_active=True,role__in=["OWNER","FINANCE","FLEET","APPROVER"]).select_related("user")
        return Response({"count": rows.count(),"page":page,"page_size":page_size, "items": [case_data(row) for row in rows[(page-1)*page_size:page*page_size]],
            "owners": [{"id": str(member.user_id), "email": member.user.email} for member in members]})

    def post(self, request):
        if not self.allowed(request):
            return Response({"error": "Fleet review access required."}, status=403)
        return Response({"created": sync_cases(request)})


class FleetExceptionDetail(APIView):
    permission_classes = [HasTenantMembership]

    def get(self, request, case_id):
        if not FleetExceptions().allowed(request):
            return Response({"error": "Fleet review access required."}, status=403)
        row = FleetExceptionCase.objects.filter(tenant=request.tenant, id=case_id).select_related("owner", "reviewed_by").first()
        if not row:
            return Response({"error": "Case not found."}, status=404)
        history = AuditLog.objects.filter(tenant=request.tenant, object_type="FleetExceptionCase", object_id=str(row.id)).select_related("actor").order_by("-created_at")[:100]
        return Response({**case_data(row), "history": [{"action": entry.action, "actor": entry.actor.email if entry.actor else None,
            "at": entry.created_at.isoformat(), "details": entry.metadata} for entry in history]})

    @transaction.atomic
    def patch(self, request, case_id):
        from .views import audit
        if not FleetExceptions().allowed(request):
            return Response({"error": "Fleet review access required."}, status=403)
        row = FleetExceptionCase.objects.select_for_update().filter(tenant=request.tenant, id=case_id).first()
        if not row:
            return Response({"error": "Case not found."}, status=404)
        if set(request.data) - {"action", "note", "public_resolution", "owner_id", "due_at", "expected_updated_at"}:
            return Response({"error": "Unsupported case field."}, status=400)
        if request.data.get("expected_updated_at") != row.updated_at.isoformat():
            return Response({"error": "This case changed. Refresh before saving."}, status=409)
        action = request.data.get("action")
        note = str(request.data.get("note", "")).strip()
        if action not in {"assign", "confirm", "dismiss", "resolve", "reopen"} or not note or len(note) > 1000:
            return Response({"error": "Choose an action and provide a review reason of 1–1000 characters."}, status=400)
        public_resolution=str(request.data.get("public_resolution","")).strip()
        if action=="resolve" and row.category=="CUSTOMER_DELIVERY_DISPUTE" and not public_resolution:
            return Response({"error":"Provide a customer-facing response before resolving this delivery issue."},status=400)
        if len(public_resolution)>1000 or (public_resolution and (action!="resolve" or row.category!="CUSTOMER_DELIVERY_DISPUTE")):
            return Response({"error":"Customer-facing responses can only be published when resolving a customer issue, up to 1000 characters."},status=400)
        before = {"status": row.status, "owner_id": str(row.owner_id) if row.owner_id else None, "due_at": row.due_at.isoformat() if row.due_at else None}
        if action == "assign":
            try:
                owner_id = UUID(str(request.data.get("owner_id")))
            except (ValueError, TypeError):
                return Response({"error": "Choose an active workspace owner for this case."}, status=400)
            member = Membership.objects.filter(tenant=request.tenant, user_id=owner_id, is_active=True,role__in=["OWNER","FINANCE","FLEET","APPROVER"]).first()
            due_at = parse_datetime(str(request.data.get("due_at", "")))
            if not member or not due_at or not timezone.is_aware(due_at):
                return Response({"error": "Choose an active workspace member and a deadline including a timezone."}, status=400)
            row.owner_id, row.due_at = owner_id, due_at
        else:
            if action in {"confirm", "dismiss"} and row.status not in {"OPEN", "CONFIRMED"}:
                return Response({"error": "Reopen the case before changing a closed review decision."}, status=409)
            if action == "resolve" and row.status not in {"OPEN", "CONFIRMED"}:
                return Response({"error": "Only an active case can be resolved."}, status=409)
            row.status = {"confirm": "CONFIRMED", "dismiss": "DISMISSED", "resolve": "RESOLVED", "reopen": "OPEN"}[action]
            row.reviewed_by, row.reviewed_at = request.user, timezone.now()
        row.review_note = note
        if public_resolution:row.public_resolution=public_resolution
        row.save()
        if action in {"confirm","resolve"} and any(key in row.category for key in ("DELAY","STOP")) and row.evidence.get("trip_id"):
            from .models import FleetTrip
            FleetTrip.objects.filter(tenant=request.tenant,id=row.evidence["trip_id"]).update(delay_reason=note[:500])
        audit(request, f"FLEET_EXCEPTION_{action.upper()}", row, {"before": before, "status": row.status,
            "owner_id": str(row.owner_id) if row.owner_id else None, "due_at": row.due_at.isoformat() if row.due_at else None, "note": note,"public_resolution":public_resolution})
        return Response(case_data(row))
