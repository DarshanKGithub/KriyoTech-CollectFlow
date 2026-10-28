from decimal import Decimal
from datetime import date, datetime, timedelta
import unicodedata
import hashlib
import json
import csv
import io
import statistics
from difflib import SequenceMatcher
from uuid import UUID, uuid4

from django.db import IntegrityError, transaction
from django.core.cache import cache
from django.db.models import Case, Count, F, Max, Prefetch, Sum, When
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.http import FileResponse, HttpResponse
from django.db.models import OuterRef, Subquery, DecimalField, Value, Q
from django.db.models.functions import Coalesce
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.views import APIView

from accounts.models import Membership
from accounts.permissions import HasTenantMembership
from audit.models import AuditLog
from documents.models import Document
from .models import DockAppointment, DriverAdvance, DriverAdvanceRecovery, DriverExpenseSettlement, DriverPayPolicy, DriverSalaryAdjustment, DriverSalaryPayment, DriverSalaryRecord, DriverTripEarning, FleetCustomer, FleetDock, FleetDriver, FleetFollowUp, FleetLogisticsDocument, FleetMaintenanceRecord, FleetTrip, FleetTripLocation, FleetVehicle, FleetVehicleDocument, FreightImportBatch, FreightImportRow, ReturnLoadOffer, TransportCollection, TransportInvoice, TransportOrder, TripExpenseLine, TripRevenueLine
from .serializers import DriverAdvanceCreateSerializer, DriverAdvanceRecoveryCreateSerializer, DriverPayPolicySerializer, DriverSalaryAdjustmentSerializer, DriverSalaryPaymentSerializer, DriverSalaryRecordSerializer, FleetCustomerSerializer, FleetDriverSerializer, FleetFollowUpSerializer, FleetTripSerializer, FleetVehicleSerializer, TransportCollectionCreateSerializer, TransportInvoiceCreateSerializer, TransportOrderSerializer, TripExpenseLineSerializer, TripRevenueLineSerializer
from .compatibility import load_compatibility


EDIT_ROLES = {Membership.Role.OWNER, Membership.Role.FINANCE, Membership.Role.PURCHASE, "FLEET"}
REVIEW_ROLES = {Membership.Role.OWNER, Membership.Role.FINANCE, Membership.Role.APPROVER}


def audit(request, action, obj, metadata=None):
    AuditLog.objects.create(tenant=request.tenant, actor=request.user, action=action, object_type=obj.__class__.__name__, object_id=str(obj.id), metadata=metadata or {})


def pay_policy_evidence(tenant, driver_id, effective_date):
    policy = DriverPayPolicy.objects.filter(tenant=tenant, driver_id=driver_id,
        effective_from__lte=effective_date).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=effective_date)).order_by("-effective_from").first()
    evidence = {"policy_id": str(policy.pk) if policy else None, "basis": policy.basis if policy else None,
        "rate": str(policy.rate) if policy else None, "effective_from": policy.effective_from.isoformat() if policy else None,
        "effective_to": policy.effective_to.isoformat() if policy and policy.effective_to else None,
        "fleet_controls": tenant.settings.get("fleet_controls", {})}
    evidence["policy_version"] = hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()[:16]
    return evidence


def filter_trips_from_request(queryset, params):
    search = params.get("search", "").strip()
    if search:
        queryset = queryset.filter(
            Q(trip_number__icontains=search) | Q(customer_reference__icontains=search)
            | Q(origin__icontains=search) | Q(destination__icontains=search)
            | Q(transport_order__order_number__icontains=search) | Q(transport_order__customer__name__icontains=search)
            | Q(vehicle__registration_number__icontains=search) | Q(driver__name__icontains=search)
        )
    if params.get("status"):
        queryset = queryset.filter(status=params["status"])
    for param, field in (("vehicle_id", "vehicle_id"), ("driver_id", "driver_id")):
        if params.get(param):
            try:
                UUID(params[param])
            except ValueError as exc:
                raise ValidationError({param: "Enter a valid ID."}) from exc
            queryset = queryset.filter(**{field: params[param]})
    for param, lookup in (("date_from", "gte"), ("date_to", "lte")):
        if params.get(param):
            try:
                date_value = date.fromisoformat(params[param])
            except ValueError as exc:
                raise ValidationError({param: "Use YYYY-MM-DD format."}) from exc
            queryset = queryset.filter(
                Q(**{f"starts_at__date__{lookup}": date_value})
                | Q(starts_at__isnull=True, **{f"created_at__date__{lookup}": date_value})
            )
    return queryset


class FleetDashboard(APIView):
    permission_classes = [HasTenantMembership]

    def get(self, request):
        if request.membership.role == Membership.Role.DRIVER:
            return Response({"error": "Fleet manager access required."}, status=403)
        tenant = request.tenant
        trips = FleetTrip.objects.filter(tenant=tenant)
        expenses = TripExpenseLine.objects.filter(tenant=tenant)
        approved_revenue = TripRevenueLine.objects.filter(tenant=tenant, status="APPROVED", is_estimated=False).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        approved_expenses = expenses.filter(status="APPROVED", is_estimated=False).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        eligible_salary = DriverSalaryRecord.objects.filter(tenant=tenant, status__in=[DriverSalaryRecord.Status.APPROVED, DriverSalaryRecord.Status.PARTIALLY_PAID, DriverSalaryRecord.Status.PAID, DriverSalaryRecord.Status.SETTLED])
        salary_due = sum((record.gross_earnings_amount for record in eligible_salary.select_related("driver")), Decimal("0.00"))
        salary_recovered = DriverAdvanceRecovery.objects.filter(tenant=tenant, salary_record__in=eligible_salary).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        salary_paid = DriverSalaryPayment.objects.filter(tenant=tenant).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        return Response({
            "active_vehicles": FleetVehicle.objects.filter(tenant=tenant, status="ACTIVE").count(),
            "active_drivers": FleetDriver.objects.filter(tenant=tenant, status="ACTIVE").count(),
            "trips_in_progress": trips.filter(status=FleetTrip.Status.IN_PROGRESS).count(),
            "trips_awaiting_review": trips.filter(status=FleetTrip.Status.SUBMITTED).count(),
            "open_follow_ups": FleetFollowUp.objects.filter(tenant=tenant, status__in=["OPEN", "IN_PROGRESS"]).count(),
            "approved_trip_revenue": f"{approved_revenue:.2f}",
            "approved_trip_expenses": f"{approved_expenses:.2f}",
            "approved_trip_margin": f"{approved_revenue - approved_expenses:.2f}",
            "driver_salary_remaining": f"{salary_due - salary_paid - salary_recovered:.2f}",
        })


class FleetDocumentUpload(APIView):
    permission_classes = [HasTenantMembership]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        if request.membership.role not in EDIT_ROLES | {Membership.Role.DRIVER}:
            return Response({"error": "Fleet edit permission required"}, status=403)
        uploaded = request.FILES.get("file")
        if not uploaded:
            return Response({"error": "Choose a receipt file."}, status=400)
        allowed = {"application/pdf", "image/jpeg", "image/png", "image/heic", "image/heif"}
        if uploaded.size > 25 * 1024 * 1024 or uploaded.content_type not in allowed:
            return Response({"error": "Receipt must be a PDF, JPEG, PNG, or HEIC file under 25 MB."}, status=400)
        kind = request.data.get("logistics_kind")
        if kind and kind not in FleetLogisticsDocument.Kind.values:
            return Response({"error": "Choose EWAY_BILL, CONSIGNMENT_NOTE or PROOF_OF_DELIVERY."}, status=400)
        digest = hashlib.sha256(uploaded.read()).hexdigest()
        uploaded.seek(0)
        document = Document.objects.create(tenant=request.tenant, filename=uploaded.name[:255], media_type=uploaded.content_type,
            checksum_sha256=digest, size_bytes=uploaded.size, uploaded_by=request.user, file=uploaded)
        audit(request, "FLEET_RECEIPT_UPLOADED", document, {"checksum": digest, "size_bytes": uploaded.size})
        if kind:
            record = FleetLogisticsDocument.objects.create(tenant=request.tenant, document=document, kind=kind)
            try:
                from .tasks import extract_logistics_document
                transaction.on_commit(lambda: extract_logistics_document.delay(str(record.id)))
            except Exception:
                record.status = FleetLogisticsDocument.Status.NEEDS_REVIEW
                record.warnings = ["Could not queue automatic extraction. Review the document manually."]
                record.save(update_fields=["status", "warnings"])
            audit(request, "FLEET_LOGISTICS_DOCUMENT_UPLOADED", record, {"kind": kind, "document_id": str(document.id)})
            return Response({"id": str(document.id), "filename": document.filename, "logistics_document_id": str(record.id), "status": record.status}, status=201)
        return Response({"id": str(document.id), "filename": document.filename}, status=201)


def _fleet_file(request, uploaded):
    allowed = {"application/pdf", "image/jpeg", "image/png", "image/heic", "image/heif"}
    if uploaded.size > 25 * 1024 * 1024 or uploaded.content_type not in allowed:
        raise ValidationError({"file": "Choose a PDF, JPEG, PNG, or HEIC file under 25 MB."})
    digest = hashlib.sha256(uploaded.read()).hexdigest()
    uploaded.seek(0)
    return Document.objects.create(tenant=request.tenant, filename=uploaded.name[:255], media_type=uploaded.content_type,
        checksum_sha256=digest, size_bytes=uploaded.size, uploaded_by=request.user, file=uploaded)


def _vehicle_document_data(row, today=None):
    today = today or timezone.localdate()
    days_left = (row.expires_on - today).days if row.expires_on else None
    return {"id": str(row.id), "vehicle_id": str(row.vehicle_id), "registration_number": row.vehicle.registration_number,
        "document_id": str(row.document_id), "filename": row.document.filename, "kind": row.kind,
        "kind_label": row.get_kind_display(), "document_number": row.document_number,
        "issued_on": row.issued_on.isoformat() if row.issued_on else None,
        "expires_on": row.expires_on.isoformat() if row.expires_on else None,
        "days_until_expiry": days_left, "notes": row.notes, "created_at": row.created_at.isoformat()}


class FleetVehicleDocuments(APIView):
    permission_classes = [HasTenantMembership]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        if request.membership.role == Membership.Role.DRIVER:
            return Response({"error": "Fleet manager access required."}, status=403)
        rows = FleetVehicleDocument.objects.filter(tenant=request.tenant).select_related("vehicle", "document").order_by("expires_on", "vehicle__registration_number")
        if request.query_params.get("vehicle_id"):
            rows = rows.filter(vehicle_id=request.query_params["vehicle_id"])
        today = timezone.localdate()
        data = [_vehicle_document_data(row, today) for row in rows[:1000]]
        for row in data:
            days = row["days_until_expiry"]
            row["status"] = "NO_EXPIRY" if days is None else "EXPIRED" if days < 0 else "DUE_SOON" if days <= 30 else "VALID"
        return Response(data)

    def post(self, request):
        if request.membership.role not in EDIT_ROLES:
            return Response({"error": "Fleet edit permission required."}, status=403)
        vehicle = FleetVehicle.objects.filter(tenant=request.tenant, id=request.data.get("vehicle_id")).first()
        if not vehicle:
            return Response({"error": "Choose a truck in this workspace."}, status=404)
        kind = request.data.get("kind")
        if kind not in FleetVehicleDocument.Kind.values:
            return Response({"error": "Choose a valid truck document type."}, status=400)
        uploaded = request.FILES.get("file")
        if not uploaded:
            return Response({"error": "Choose a document file."}, status=400)
        def parse_optional_date(field):
            value = request.data.get(field) or None
            if not value: return None
            try: return date.fromisoformat(value)
            except (TypeError, ValueError): raise ValidationError({field: "Use YYYY-MM-DD format."})
        issued = parse_optional_date("issued_on")
        expires = parse_optional_date("expires_on")
        if issued and expires and expires < issued:
            return Response({"expires_on": "Expiry date cannot be before the issue date."}, status=400)
        document = _fleet_file(request, uploaded)
        row = FleetVehicleDocument.objects.create(tenant=request.tenant, vehicle=vehicle, document=document, kind=kind,
            document_number=str(request.data.get("document_number", ""))[:100], issued_on=issued, expires_on=expires,
            notes=str(request.data.get("notes", ""))[:5000], uploaded_by=request.user)
        audit(request, "FLEET_VEHICLE_DOCUMENT_UPLOADED", row, {"kind": kind, "document_id": str(document.id)})
        return Response(_vehicle_document_data(row), status=201)


class FleetVehicleDocumentDownload(APIView):
    permission_classes = [HasTenantMembership]

    def get(self, request, record_id):
        if request.membership.role == Membership.Role.DRIVER:
            return Response({"error": "Fleet manager access required."}, status=403)
        row = FleetVehicleDocument.objects.filter(tenant=request.tenant, id=record_id).select_related("document").first()
        if not row: return Response({"error": "Truck document not found."}, status=404)
        try: handle = row.document.file.open("rb")
        except (OSError, ValueError): return Response({"error": "The stored document file is unavailable."}, status=404)
        return FileResponse(handle, as_attachment=True, filename=row.document.filename, content_type=row.document.media_type)


def _maintenance_data(row):
    return {"id": str(row.id), "vehicle_id": str(row.vehicle_id), "registration_number": row.vehicle.registration_number,
        "category": row.category, "category_label": row.get_category_display(), "description": row.description,
        "failure_code": row.failure_code, "breakdown_at": row.breakdown_at.isoformat() if row.breakdown_at else None,
        "returned_to_service_at": row.returned_to_service_at.isoformat() if row.returned_to_service_at else None,
        "downtime_hours": round(((row.returned_to_service_at or timezone.now()) - row.breakdown_at).total_seconds() / 3600, 2) if row.breakdown_at else None,
        "service_date": row.service_date.isoformat(), "odometer_km": str(row.odometer_km) if row.odometer_km is not None else None,
        "cost": f"{row.cost:.2f}", "vendor": row.vendor, "next_due_date": row.next_due_date.isoformat() if row.next_due_date else None,
        "next_due_odometer_km": str(row.next_due_odometer_km) if row.next_due_odometer_km is not None else None,
        "notes": row.notes, "receipt_filename": row.receipt.filename if row.receipt_id else None, "created_at": row.created_at.isoformat()}


class FleetMaintenance(APIView):
    permission_classes = [HasTenantMembership]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        if request.membership.role == Membership.Role.DRIVER:
            return Response({"error": "Fleet manager access required."}, status=403)
        rows = FleetMaintenanceRecord.objects.filter(tenant=request.tenant).select_related("vehicle", "receipt").order_by("-service_date", "-created_at")
        if request.query_params.get("vehicle_id"):
            rows = rows.filter(vehicle_id=request.query_params["vehicle_id"])
        return Response([_maintenance_data(row) for row in rows[:1000]])

    def post(self, request):
        if request.membership.role not in EDIT_ROLES:
            return Response({"error": "Fleet edit permission required."}, status=403)
        vehicle = FleetVehicle.objects.filter(tenant=request.tenant, id=request.data.get("vehicle_id")).first()
        if not vehicle: return Response({"error": "Choose a truck in this workspace."}, status=404)
        category = request.data.get("category", FleetMaintenanceRecord.Category.SERVICE)
        if category not in FleetMaintenanceRecord.Category.values:
            return Response({"category": "Choose a valid maintenance category."}, status=400)
        try:
            service_date = date.fromisoformat(request.data.get("service_date", ""))
            next_due_date = date.fromisoformat(request.data["next_due_date"]) if request.data.get("next_due_date") else None
            cost = Decimal(str(request.data.get("cost") or "0"))
            odometer = Decimal(str(request.data["odometer_km"])) if request.data.get("odometer_km") else None
            next_odometer = Decimal(str(request.data["next_due_odometer_km"])) if request.data.get("next_due_odometer_km") else None
            if not cost.is_finite() or cost < 0 or any(v is not None and (not v.is_finite() or v < 0) for v in (odometer, next_odometer)):
                raise ValueError
        except (TypeError, ValueError, ArithmeticError):
            return Response({"error": "Enter valid dates and non-negative cost/odometer values."}, status=400)
        description = str(request.data.get("description", "")).strip()
        if not description: return Response({"description": "Describe the service or repair."}, status=400)
        breakdown_at = parse_datetime(str(request.data["breakdown_at"])) if request.data.get("breakdown_at") else None
        returned_at = parse_datetime(str(request.data["returned_to_service_at"])) if request.data.get("returned_to_service_at") else None
        if (request.data.get("breakdown_at") and (not breakdown_at or not timezone.is_aware(breakdown_at))) or (request.data.get("returned_to_service_at") and (not returned_at or not timezone.is_aware(returned_at))):
            return Response({"error": "Breakdown and return timestamps must include a timezone."}, status=400)
        if (returned_at and not breakdown_at) or (breakdown_at and returned_at and returned_at < breakdown_at) or (breakdown_at and breakdown_at > timezone.now()) or (returned_at and returned_at > timezone.now()):
            return Response({"error": "Return must follow breakdown; breakdown cannot be in the future."}, status=400)
        receipt = _fleet_file(request, request.FILES["receipt"]) if request.FILES.get("receipt") else None
        row = FleetMaintenanceRecord.objects.create(tenant=request.tenant, vehicle=vehicle, category=category,
            description=description[:240], service_date=service_date, odometer_km=odometer, cost=cost,
            vendor=str(request.data.get("vendor", ""))[:180], next_due_date=next_due_date,
            next_due_odometer_km=next_odometer, notes=str(request.data.get("notes", ""))[:5000],
            receipt=receipt, created_by=request.user, failure_code=str(request.data.get("failure_code", "")).strip().upper()[:64],
            breakdown_at=breakdown_at, returned_to_service_at=returned_at)
        audit(request, "FLEET_MAINTENANCE_RECORDED", row, {"category": category, "cost": f"{cost:.2f}", "vehicle_id": str(vehicle.id)})
        return Response(_maintenance_data(row), status=201)


class FleetLogisticsDocuments(APIView):
    permission_classes = [HasTenantMembership]

    def get(self, request):
        if request.membership.role not in EDIT_ROLES | REVIEW_ROLES:
            return Response({"error": "Fleet document review access required."}, status=403)
        rows = FleetLogisticsDocument.objects.filter(tenant=request.tenant).select_related("document", "trip", "transport_order").order_by("-created_at")[:500]
        return Response([logistics_document_data(row) for row in rows])

    @transaction.atomic
    def post(self, request, record_id):
        if request.membership.role not in EDIT_ROLES | REVIEW_ROLES:
            return Response({"error": "Fleet document review access required."}, status=403)
        if set(request.data) - {"trip_id", "order_id", "fields", "confirm"}:
            return Response({"error": "Unsupported document review field."}, status=400)
        record = FleetLogisticsDocument.objects.select_for_update().select_related("document").filter(tenant=request.tenant, id=record_id).first()
        if not record: return Response({"error": "Logistics document not found."}, status=404)
        fields = request.data.get("fields", record.extracted_fields)
        if not isinstance(fields, dict): return Response({"error": "Document fields must be an object."}, status=400)
        if len(json.dumps(fields, default=str)) > 10000: return Response({"error": "Document fields are too large."}, status=400)
        record.extracted_fields = fields
        if request.data.get("trip_id"):
            record.trip = FleetTrip.objects.filter(tenant=request.tenant, id=request.data["trip_id"]).first()
            if not record.trip: return Response({"error": "Trip not found in this workspace."}, status=404)
            record.transport_order = record.trip.transport_order
        if request.data.get("order_id"):
            record.transport_order = TransportOrder.objects.filter(tenant=request.tenant, id=request.data["order_id"]).first()
            if not record.transport_order: return Response({"error": "Transport order not found in this workspace."}, status=404)
            if record.trip_id and record.trip.transport_order_id != record.transport_order_id:
                return Response({"error": "The selected trip and transport order do not belong together."}, status=400)
            record.trip = FleetTrip.objects.filter(tenant=request.tenant, transport_order=record.transport_order).first()
        if request.data.get("confirm") is True:
            if record.status == FleetLogisticsDocument.Status.CONFIRMED:
                return Response(logistics_document_data(record))
            if record.status not in {FleetLogisticsDocument.Status.NEEDS_REVIEW, FleetLogisticsDocument.Status.FAILED}:
                return Response({"error": "Wait until extraction finishes before confirming."}, status=409)
            if not record.trip and not record.transport_order:
                return Response({"error": "Link the document to a trip or transport order before confirming."}, status=400)
            record.status = FleetLogisticsDocument.Status.CONFIRMED
            record.confirmed_by = request.user
            record.confirmed_at = timezone.now()
            if record.kind == FleetLogisticsDocument.Kind.PROOF_OF_DELIVERY and record.trip:
                record.trip.delivery_proof = record.document
                if fields.get("received_by"):
                    record.trip.delivery_signature_name = str(fields["received_by"])[:160]
                record.trip.save(update_fields=["delivery_proof", "delivery_signature_name", "updated_at"])
        record.save()
        audit(request, "FLEET_LOGISTICS_DOCUMENT_REVIEWED", record, {"kind": record.kind, "status": record.status, "trip_id": str(record.trip_id) if record.trip_id else None, "order_id": str(record.transport_order_id) if record.transport_order_id else None})
        return Response(logistics_document_data(record))


def logistics_document_data(row):
    return {"id": str(row.id), "document_id": str(row.document_id), "filename": row.document.filename,
        "kind": row.kind, "status": row.status, "trip_id": str(row.trip_id) if row.trip_id else None,
        "trip_number": row.trip.trip_number if row.trip_id else "", "order_id": str(row.transport_order_id) if row.transport_order_id else None,
        "order_number": row.transport_order.order_number if row.transport_order_id else "", "fields": row.extracted_fields,
        "confidence": row.confidence, "warnings": row.warnings, "created_at": row.created_at.isoformat()}


class FleetDirectory(APIView):
    permission_classes = [HasTenantMembership]

    def get(self, request, kind):
        if request.membership.role == Membership.Role.DRIVER:
            return Response({"error": "Fleet directory access required."}, status=403)
        if kind == "vehicles":
            rows = FleetVehicle.objects.filter(tenant=request.tenant).order_by("registration_number")
            return Response(FleetVehicleSerializer(rows, many=True).data)
        if kind == "drivers":
            rows = FleetDriver.objects.filter(tenant=request.tenant).select_related("user").order_by("name")
            return Response(FleetDriverSerializer(rows, many=True, context={"tenant": request.tenant}).data)
        return Response({"error": "Unknown fleet directory"}, status=404)

    def post(self, request, kind):
        if request.membership.role not in EDIT_ROLES:
            return Response({"error": "Fleet edit permission required"}, status=403)
        serializer_class = FleetVehicleSerializer if kind == "vehicles" else FleetDriverSerializer if kind == "drivers" else None
        if serializer_class is None:
            return Response({"error": "Unknown fleet directory"}, status=404)
        serializer = serializer_class(data=request.data, context={"tenant": request.tenant})
        serializer.is_valid(raise_exception=True)
        try:
            instance = serializer.save(tenant=request.tenant)
        except IntegrityError:
            return Response({"error": "A record with this registration or reference already exists."}, status=409)
        audit(request, f"FLEET_{kind[:-1].upper()}_CREATED", instance)
        return Response(serializer.data, status=201)


class FleetDirectoryDetail(APIView):
    permission_classes = [HasTenantMembership]

    def patch(self, request, kind, object_id):
        if request.membership.role not in EDIT_ROLES:
            return Response({"error": "Fleet edit permission required"}, status=403)
        model, serializer_class = (FleetVehicle, FleetVehicleSerializer) if kind == "vehicles" else (FleetDriver, FleetDriverSerializer) if kind == "drivers" else (None, None)
        if model is None:
            return Response({"error": "Unknown fleet directory"}, status=404)
        obj = get_object_or_404(model, tenant=request.tenant, id=object_id)
        serializer = serializer_class(obj, data=request.data, partial=True, context={"tenant": request.tenant})
        serializer.is_valid(raise_exception=True)
        try:
            obj = serializer.save()
        except IntegrityError:
            return Response({"error": "A record with this registration or reference already exists."}, status=409)
        audit(request, f"FLEET_{kind[:-1].upper()}_UPDATED", obj)
        return Response(serializer.data)


class FleetCustomers(APIView):
    permission_classes = [HasTenantMembership]

    def get(self, request):
        if request.membership.role == Membership.Role.DRIVER:
            return Response({"error": "Fleet directory access required."}, status=403)
        rows = FleetCustomer.objects.filter(tenant=request.tenant).order_by("name")
        return Response(FleetCustomerSerializer(rows, many=True).data)

    def post(self, request):
        if request.membership.role not in EDIT_ROLES:
            return Response({"error": "Fleet edit permission required"}, status=403)
        serializer = FleetCustomerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        customer = serializer.save(tenant=request.tenant)
        audit(request, "FLEET_CUSTOMER_CREATED", customer)
        return Response(FleetCustomerSerializer(customer).data, status=201)


class FleetCustomerDetail(APIView):
    permission_classes = [HasTenantMembership]

    def patch(self, request, customer_id):
        if request.membership.role not in EDIT_ROLES:
            return Response({"error": "Fleet edit permission required"}, status=403)
        customer = get_object_or_404(FleetCustomer, tenant=request.tenant, id=customer_id)
        serializer = FleetCustomerSerializer(customer, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        customer = serializer.save()
        audit(request, "FLEET_CUSTOMER_UPDATED", customer)
        return Response(serializer.data)


class TransportOrders(APIView):
    permission_classes = [HasTenantMembership]

    def get(self, request):
        if request.membership.role == Membership.Role.DRIVER:
            return Response({"error": "Fleet dispatch access required."}, status=403)
        rows = TransportOrder.objects.filter(tenant=request.tenant).select_related("customer").order_by("-created_at")
        if request.query_params.get("status"):
            rows = rows.filter(status=request.query_params["status"])
        return Response(TransportOrderSerializer(rows, many=True, context={"tenant": request.tenant}).data)

    def post(self, request):
        if request.membership.role not in EDIT_ROLES:
            return Response({"error": "Fleet edit permission required"}, status=403)
        serializer = TransportOrderSerializer(data=request.data, context={"tenant": request.tenant})
        serializer.is_valid(raise_exception=True)
        try:
            order = serializer.save(tenant=request.tenant, created_by=request.user)
        except IntegrityError:
            return Response({"error": "An order with this number already exists in this workspace."}, status=409)
        audit(request, "TRANSPORT_ORDER_CREATED", order, {"customer_id": str(order.customer_id)})
        return Response(TransportOrderSerializer(order, context={"tenant": request.tenant}).data, status=201)


def transport_invoice_data(invoice):
    collections = list(invoice.collections.all())
    paid = sum((collection.amount for collection in collections), Decimal("0.00"))
    return {
        "id": str(invoice.id), "invoice_number": invoice.invoice_number,
        "customer": {"id": str(invoice.customer_id), "name": invoice.customer.name},
        "order": {"id": str(invoice.order_id), "order_number": invoice.order.order_number},
        "trip": {"id": str(invoice.trip_id), "trip_number": invoice.trip.trip_number},
        "invoice_date": invoice.invoice_date.isoformat(),
        "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
        "amount": f"{invoice.amount:.2f}", "paid_amount": f"{paid:.2f}",
        "outstanding_amount": f"{max(invoice.amount - paid, Decimal('0.00')):.2f}",
        "status": invoice.status, "notes": invoice.notes,
        "collections": [{"id": str(c.id), "amount": f"{c.amount:.2f}", "received_date": c.received_date.isoformat(), "method": c.method, "reference": c.reference, "source_account": str(c.source_account_id) if c.source_account_id else None, "currency": c.currency, "provenance_note": c.provenance_note} for c in sorted(collections, key=lambda item: (item.received_date, item.created_at), reverse=True)],
    }


class TransportInvoices(APIView):
    permission_classes = [HasTenantMembership]

    def get(self, request):
        if request.membership.role == Membership.Role.DRIVER:
            return Response({"error": "Customer billing access required."}, status=403)
        rows = TransportInvoice.objects.filter(tenant=request.tenant).select_related("customer", "order", "trip").prefetch_related("collections").order_by("-created_at")
        return Response([transport_invoice_data(row) for row in rows])

    @transaction.atomic
    def post(self, request):
        if request.membership.role not in EDIT_ROLES | REVIEW_ROLES:
            return Response({"error": "Customer billing permission required."}, status=403)
        serializer = TransportInvoiceCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        trip = get_object_or_404(FleetTrip.objects.select_for_update(of=("self",)).select_related("transport_order__customer"), tenant=request.tenant, id=serializer.validated_data["trip_id"])
        order = get_object_or_404(TransportOrder.objects.select_for_update(), pk=trip.transport_order_id, tenant=request.tenant) if trip.transport_order_id else None
        if order is None:
            return Response({"error": "Link this trip to a customer transport order before billing."}, status=400)
        if trip.delivery_at is None or order.status != TransportOrder.Status.DELIVERED:
            return Response({"error": "Only delivered trips can be invoiced."}, status=400)
        if not trip.delivery_proof_id and not trip.delivery_signature_name.strip():
            return Response({"error": "Record delivery proof or customer signature before creating the invoice."}, status=400)
        if order.agreed_amount is None or order.agreed_amount <= 0:
            return Response({"error": "Add a positive agreed amount to the transport order before billing."}, status=400)
        invoice_number = serializer.validated_data.get("invoice_number", "").strip() or f"TR-{order.order_number}"
        if TransportInvoice.objects.filter(tenant=request.tenant, order=order).exists():
            return Response({"error": "An invoice already exists for this transport order."}, status=409)
        if TransportInvoice.objects.filter(tenant=request.tenant, invoice_number=invoice_number).exists():
            return Response({"error": "That customer invoice number is already in use."}, status=409)
        if TripRevenueLine.objects.filter(tenant=request.tenant,trip=trip,detention_appointment__isnull=False).exclude(status=TripRevenueLine.ReviewStatus.APPROVED).exists():
            return Response({"error":"Approve the trip's pending detention revenue through the trip review workflow before invoicing."},status=409)
        try:
            detention_total = TripRevenueLine.objects.filter(tenant=request.tenant, trip=trip,
                detention_appointment__isnull=False, status=TripRevenueLine.ReviewStatus.APPROVED, is_estimated=False).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
            invoice = TransportInvoice.objects.create(
                tenant=request.tenant, customer=order.customer, order=order, trip=trip,
                invoice_number=invoice_number, invoice_date=serializer.validated_data.get("invoice_date", timezone.localdate()),
                due_date=serializer.validated_data.get("due_date"), amount=order.agreed_amount + detention_total,
                notes=serializer.validated_data.get("notes", ""), created_by=request.user,
            )
        except IntegrityError:
            return Response({"error": "An invoice already exists for this order or invoice number."}, status=409)
        audit(request, "TRANSPORT_CUSTOMER_INVOICE_CREATED", invoice, {"trip_id": str(trip.id), "order_id": str(order.id), "amount": str(invoice.amount)})
        return Response(transport_invoice_data(invoice), status=201)


class FleetRevenueLeakage(APIView):
    """Read-only, evidence-backed review of unbilled freight and receivable variances."""
    permission_classes = [HasTenantMembership]

    def get(self, request):
        if request.membership.role not in EDIT_ROLES | REVIEW_ROLES:
            return Response({"error": "Fleet finance access required."}, status=403)
        tenant = request.tenant
        today = timezone.localdate()
        delivered = FleetTrip.objects.filter(tenant=tenant, delivery_at__isnull=False,
            transport_order__status=TransportOrder.Status.DELIVERED).select_related(
                "vehicle", "driver", "transport_order__customer").prefetch_related(
                Prefetch("revenue_lines", queryset=TripRevenueLine.objects.filter(
                    tenant=tenant, status=TripRevenueLine.ReviewStatus.APPROVED, is_estimated=False), to_attr="_approved_actual_revenue"))
        trip_rows = list(delivered[:2000])
        trip_ids = [trip.id for trip in trip_rows]
        invoices = list(TransportInvoice.objects.filter(tenant=tenant, trip_id__in=trip_ids)
            .select_related("customer", "order").prefetch_related("collections"))
        invoices_by_trip = {invoice.trip_id: invoice for invoice in invoices}
        detention_totals = {row["trip_id"]:row["total"] for row in TripRevenueLine.objects.filter(tenant=tenant,trip_id__in=trip_ids,
            detention_appointment__isnull=False,status="APPROVED",is_estimated=False).values("trip_id").annotate(total=Sum("amount"))}
        collection_ids = [collection.id for invoice in invoices for collection in invoice.collections.all()]
        bank_status = {}
        if collection_ids:
            from phase3.models import BankTransaction, ReconciliationGroupTarget
            bank_status = {str(row["transport_collection_id"]): row["status"] for row in BankTransaction.objects.filter(
                tenant=tenant, transport_collection_id__in=collection_ids,status="RECONCILED").values("transport_collection_id", "status")}
            for collection_id in ReconciliationGroupTarget.objects.filter(group__tenant=tenant,group__status="RECONCILED",active=True,
                transport_collection_id__in=collection_ids).values_list("transport_collection_id",flat=True):
                bank_status[str(collection_id)]="RECONCILED"
        items = []
        for trip in trip_rows:
            order = trip.transport_order
            invoice = invoices_by_trip.get(trip.id)
            actual_revenue = sum((line.amount for line in getattr(trip, "_approved_actual_revenue", [])), Decimal("0.00"))
            expected = order.agreed_amount + detention_totals.get(trip.id,Decimal("0")) if order.agreed_amount is not None else None
            base = {"trip_id": str(trip.id), "trip_number": trip.trip_number, "vehicle": trip.vehicle.registration_number,
                "customer": order.customer.name, "order_id": str(order.id), "order_number": order.order_number,
                "expected_amount": f"{expected:.2f}" if expected is not None else None,
                "approved_trip_revenue": f"{actual_revenue:.2f}",
                "delivery_at": trip.delivery_at.isoformat() if trip.delivery_at else None,
                "delivery_proof_present": bool(trip.delivery_proof_id or trip.delivery_signature_name.strip()),
                "invoice_id": str(invoice.id) if invoice else None,
                "invoice_number": invoice.invoice_number if invoice else None}
            if not invoice:
                reasons = []
                if expected is None or expected <= 0: reasons.append("Transport order has no positive agreed freight amount.")
                if not base["delivery_proof_present"]: reasons.append("Delivery proof or recipient signature is missing.")
                ready = expected is not None and expected > 0 and base["delivery_proof_present"]
                items.append({**base, "id": f"unbilled:{trip.id}", "issue": "UNBILLED_DELIVERY", "severity": "HIGH" if ready else "MEDIUM",
                    "message": "Delivered trip has no customer invoice." if ready else "Delivered trip is not invoiced and needs the listed prerequisites.",
                    "next_action": "Create draft invoice" if ready else "Resolve prerequisites before billing.", "reasons": reasons})
            if expected is not None and actual_revenue > 0 and actual_revenue != expected:
                items.append({**base, "id": f"revenue-variance:{trip.id}", "issue": "FREIGHT_REVENUE_VARIANCE", "severity": "MEDIUM",
                    "message": "Approved trip revenue differs from the transport order agreed amount.",
                    "next_action": "Review the approved revenue lines and agreed freight amount.", "reasons": ["This is a comparison only; KriyoPay does not change either amount automatically."]})
            if expected is not None and expected>0 and actual_revenue==0:
                items.append({**base,"id":f"missing-revenue:{trip.id}","issue":"MISSING_APPROVED_FREIGHT_REVENUE","severity":"MEDIUM",
                    "message":"Delivered order has an agreed freight amount but no approved actual trip revenue.",
                    "next_action":"Record or review freight revenue against the trip, checking staged freight imports before adding a line.",
                    "reasons":["Unapproved revenue is excluded from this comparison."]})
            if invoice:
                collected = sum((collection.amount for collection in invoice.collections.all()), Decimal("0.00"))
                outstanding = max(invoice.amount - collected, Decimal("0.00"))
                if expected is not None and invoice.amount != expected:
                    items.append({**base, "id": f"invoice-variance:{invoice.id}", "issue": "INVOICE_AMOUNT_VARIANCE", "severity": "MEDIUM",
                        "invoice_amount": f"{invoice.amount:.2f}", "message": "Customer invoice amount differs from the agreed order amount.",
                        "next_action": "Review the invoice and order before changing billing records.", "reasons": []})
                if invoice.due_date and invoice.due_date < today and outstanding > 0 and invoice.status != TransportInvoice.Status.CANCELLED:
                    items.append({**base, "id": f"overdue-receivable:{invoice.id}", "issue": "OVERDUE_RECEIVABLE", "severity": "HIGH",
                        "invoice_amount": f"{invoice.amount:.2f}", "paid_amount": f"{collected:.2f}", "outstanding_amount": f"{outstanding:.2f}",
                        "due_date": invoice.due_date.isoformat(), "message": "Customer invoice is past due with an outstanding balance.",
                        "next_action": "Follow up with the customer and reconcile the collection.", "reasons": []})
                if collected > 0 and outstanding > 0 and invoice.status != TransportInvoice.Status.CANCELLED:
                    items.append({**base,"id":f"partial-collection:{invoice.id}","issue":"PARTIAL_CUSTOMER_COLLECTION","severity":"MEDIUM",
                        "invoice_amount":f"{invoice.amount:.2f}","paid_amount":f"{collected:.2f}","outstanding_amount":f"{outstanding:.2f}",
                        "message":f"Customer collections cover only part of this invoice; ₹{outstanding:.2f} remains unallocated.",
                        "next_action":"Confirm whether this is a planned instalment, short payment or disputed deduction before changing the ledger.",
                        "reasons":["No deduction, discount or write-off has been assumed or posted."]})
                for collection in invoice.collections.all():
                    if collection.method == TransportCollection.Method.BANK and bank_status.get(str(collection.id)) != "RECONCILED":
                        items.append({**base, "id": f"collection-unreconciled:{collection.id}", "issue": "COLLECTION_NOT_BANK_RECONCILED", "severity": "MEDIUM",
                            "collection_id": str(collection.id), "collection_amount": f"{collection.amount:.2f}", "message": "Recorded bank collection has no confirmed matching bank statement row.",
                            "next_action": "Match and confirm this collection in Bank reconciliation.", "reasons": [f"Reference: {collection.reference or 'not provided'}", f"Date: {collection.received_date.isoformat()}"]})
        counts = {}
        exposure = Decimal("0.00")
        for item in items:
            counts[item["issue"]] = counts.get(item["issue"], 0) + 1
            exposure += Decimal(str(item.get("outstanding_amount") or item.get("expected_amount") or "0")) if item["issue"] in {"UNBILLED_DELIVERY", "OVERDUE_RECEIVABLE"} else Decimal("0.00")
        return Response({"as_of": today.isoformat(), "delivered_trip_count": len(trip_rows), "exception_count": len(items),
            "potential_exposure": f"{exposure:.2f}", "counts": counts, "items": items[:1000],
            "money_movement_enabled": False, "note": "Evidence-based review only. No invoices, collections, or financial values are modified automatically."})


class TransportInvoiceIssue(APIView):
    permission_classes = [HasTenantMembership]

    @transaction.atomic
    def post(self, request, invoice_id):
        if request.membership.role not in EDIT_ROLES | REVIEW_ROLES:
            return Response({"error": "Customer billing permission required."}, status=403)
        invoice = get_object_or_404(TransportInvoice.objects.select_for_update().select_related("customer", "order", "trip").prefetch_related("collections"), tenant=request.tenant, id=invoice_id)
        if invoice.status != TransportInvoice.Status.DRAFT:
            return Response({"error": "Only draft customer invoices can be issued."}, status=409)
        invoice.status = TransportInvoice.Status.ISSUED
        invoice.issued_at = timezone.now()
        invoice.issued_by = request.user
        invoice.save(update_fields=["status", "issued_at", "issued_by", "updated_at"])
        audit(request, "TRANSPORT_CUSTOMER_INVOICE_ISSUED", invoice, {"invoice_number": invoice.invoice_number})
        return Response(transport_invoice_data(invoice))


class TransportInvoiceCollections(APIView):
    permission_classes = [HasTenantMembership]

    @transaction.atomic
    def post(self, request, invoice_id):
        if request.membership.role not in EDIT_ROLES | REVIEW_ROLES:
            return Response({"error": "Customer collection permission required."}, status=403)
        invoice = get_object_or_404(TransportInvoice.objects.select_for_update().select_related("customer", "order", "trip"), tenant=request.tenant, id=invoice_id)
        serializer = TransportCollectionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        key = serializer.validated_data.get("idempotency_key")
        if key:
            duplicate = TransportCollection.objects.filter(tenant=request.tenant, idempotency_key=key).first()
            if duplicate:
                if duplicate.invoice_id != invoice.id:
                    return Response({"error": "This request key was already used for another collection."}, status=409)
                return Response(transport_invoice_data(invoice), status=200)
        if invoice.status not in {TransportInvoice.Status.ISSUED, TransportInvoice.Status.PARTIALLY_PAID}:
            return Response({"error": "Collections can only be recorded against issued invoices."}, status=400)
        paid = invoice.collections.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        amount = serializer.validated_data["amount"]
        if amount > invoice.amount - paid:
            return Response({"error": f"Collection exceeds the outstanding balance of ₹{invoice.amount - paid:.2f}."}, status=400)
        try:
            collection = TransportCollection.objects.create(tenant=request.tenant, invoice=invoice, created_by=request.user, **serializer.validated_data)
        except IntegrityError:
            return Response({"error": "This collection request was already recorded."}, status=409)
        paid += collection.amount
        invoice.status = TransportInvoice.Status.PAID if paid == invoice.amount else TransportInvoice.Status.PARTIALLY_PAID
        invoice.save(update_fields=["status", "updated_at"])
        audit(request, "TRANSPORT_CUSTOMER_COLLECTION_RECORDED", collection, {"invoice_id": str(invoice.id), "amount": str(collection.amount), "reference": collection.reference})
        invoice = TransportInvoice.objects.select_related("customer", "order", "trip").prefetch_related("collections").get(id=invoice.id)
        return Response(transport_invoice_data(invoice), status=201)


class TripCollection(APIView):
    permission_classes = [HasTenantMembership]

    def get(self, request):
        rows = FleetTrip.objects.filter(tenant=request.tenant).select_related("vehicle", "driver", "transport_order__customer", "driver_earning").prefetch_related("revenue_lines", "expense_lines").order_by("-created_at")
        if request.membership.role == Membership.Role.DRIVER:
            rows = rows.filter(driver__user=request.user)
        rows = filter_trips_from_request(rows, request.query_params)
        return Response(FleetTripSerializer(rows, many=True, context={"tenant": request.tenant}).data)

    @transaction.atomic
    def post(self, request):
        if request.membership.role not in EDIT_ROLES:
            return Response({"error": "Fleet edit permission required"}, status=403)
        serializer = FleetTripSerializer(data=request.data, context={"tenant": request.tenant})
        serializer.is_valid(raise_exception=True)
        values=serializer.validated_data
        if values.get("transport_order"):
            order=TransportOrder.objects.select_for_update().get(tenant=request.tenant,id=values["transport_order"].id)
            if order.status!="OPEN" or FleetTrip.objects.filter(tenant=request.tenant,transport_order=order).exists():
                return Response({"error":"This transport order is already assigned or is no longer open."},status=409)
        vehicle=FleetVehicle.objects.select_for_update().get(tenant=request.tenant,id=values["vehicle"].id)
        driver=FleetDriver.objects.select_for_update().get(tenant=request.tenant,id=values["driver"].id)
        if FleetTrip.objects.filter(tenant=request.tenant,status__in=["DRAFT","IN_PROGRESS","SUBMITTED"]).filter(Q(vehicle=vehicle)|Q(driver=driver)).exists():
            return Response({"error":"The truck or driver already has an active trip. Complete or review that trip before assigning another."},status=409)
        if FleetMaintenanceRecord.objects.filter(tenant=request.tenant,vehicle=vehicle,breakdown_at__isnull=False,returned_to_service_at__isnull=True).exists():
            return Response({"error":"This truck has an open breakdown. Record its return to service before dispatch."},status=409)
        try:
            trip = serializer.save(tenant=request.tenant, created_by=request.user)
            if trip.transport_order_id:
                TransportOrder.objects.filter(id=trip.transport_order_id, tenant=request.tenant).update(status=TransportOrder.Status.ASSIGNED, updated_at=timezone.now())
        except IntegrityError:
            return Response({"error": "A trip with this number already exists in this workspace."}, status=409)
        audit(request, "FLEET_TRIP_CREATED", trip)
        return Response(FleetTripSerializer(trip, context={"tenant": request.tenant}).data, status=201)


def normalize_location(value):
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return " ".join("".join(char if char.isalnum() else " " for char in normalized).split())


def location_match_score(left, right):
    a, b = normalize_location(left), normalize_location(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    token_a, token_b = set(a.split()), set(b.split())
    token_score = len(token_a & token_b) / max(1, len(token_a | token_b))
    sequence_score = SequenceMatcher(None, a, b).ratio()
    return max(token_score, sequence_score)


def freight_import_row_data(row):
    return {"id": str(row.id), "batch_id": str(row.batch_id), "filename": row.batch.filename,
        "row_number": row.row_number, "raw_data": row.raw_data, "trip_id": str(row.trip_id) if row.trip_id else None,
        "trip_number": row.trip.trip_number if row.trip_id else "", "kind": row.kind, "category": row.category,
        "description": row.description, "amount": str(row.amount) if row.amount is not None else None,
        "quantity_litres": str(row.quantity_litres) if row.quantity_litres is not None else None,
        "incurred_at": row.incurred_at.isoformat() if row.incurred_at else None, "status": row.status,
        "review_note": row.review_note}


class FreightImports(APIView):
    permission_classes = [HasTenantMembership]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        if request.membership.role not in EDIT_ROLES | REVIEW_ROLES:
            return Response({"error": "Freight reconciliation access required."}, status=403)
        rows = FreightImportRow.objects.filter(tenant=request.tenant).select_related("batch", "trip").order_by("-batch__created_at", "row_number")[:1000]
        return Response({"rows": [freight_import_row_data(row) for row in rows], "count": len(rows)})

    @transaction.atomic
    def post(self, request):
        if request.membership.role not in EDIT_ROLES:
            return Response({"error": "Freight import permission required."}, status=403)
        uploaded = request.FILES.get("file")
        if not uploaded or uploaded.size > 20 * 1024 * 1024:
            return Response({"error": "Choose a CSV or Excel file under 20 MB."}, status=400)
        filename = uploaded.name[:255]
        raw = uploaded.read()
        digest = hashlib.sha256(raw).hexdigest()
        existing = FreightImportBatch.objects.filter(tenant=request.tenant, checksum_sha256=digest).first()
        if existing:
            rows = existing.rows.select_related("batch", "trip").order_by("row_number")
            return Response({"batch_id": str(existing.id), "status": existing.status, "duplicate_upload": True, "rows": [freight_import_row_data(row) for row in rows]}, status=200)
        try:
            if filename.lower().endswith(".csv"):
                decoded = raw.decode("utf-8-sig")
                parsed = list(csv.DictReader(io.StringIO(decoded)))
            elif filename.lower().endswith((".xlsx", ".xlsm")):
                from openpyxl import load_workbook
                workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
                sheet = workbook.active
                matrix = sheet.iter_rows(values_only=True)
                headings = [str(value or "").strip() for value in next(matrix, ())]
                parsed = [dict(zip(headings, values)) for values in matrix if any(value is not None for value in values)]
            else:
                return Response({"error": "Use .csv or .xlsx format."}, status=400)
        except Exception:
            return Response({"error": "Could not read the file. Check that it has a header row and valid CSV or XLSX content."}, status=400)
        if not parsed or len(parsed) > 10000:
            return Response({"error": "The import must contain 1–10,000 data rows."}, status=400)
        def key(value):
            return "".join(char for char in str(value or "").strip().casefold() if char.isalnum())
        batch = FreightImportBatch.objects.create(tenant=request.tenant, filename=filename, checksum_sha256=digest, uploaded_by=request.user)
        aliases = {
            "trip": {"tripnumber", "tripid", "tripreference", "tripno"},
            "kind": {"type", "kind", "linetype", "recordtype"},
            "amount": {"amount", "total", "cost", "revenue", "expenseamount"},
            "description": {"description", "particulars", "details", "narration"},
            "category": {"category", "expensecategory"},
            "date": {"date", "incurredat", "transactiondate"},
            "litres": {"litres", "quantitylitres", "fuelquantity"},
        }
        created = []
        for number, source in enumerate(parsed, 2):
            data = {key(k): v for k, v in source.items()}
            values = {field: next((data[a] for a in names if a in data), None) for field, names in aliases.items()}
            raw_data = {str(k)[:100]: (v.isoformat() if hasattr(v, "isoformat") else str(v)[:500]) if v is not None else "" for k, v in source.items()}
            note = ""
            trip_ref = str(values["trip"] or "").strip()
            trip = FleetTrip.objects.filter(tenant=request.tenant).filter(Q(trip_number__iexact=trip_ref) | Q(customer_reference__iexact=trip_ref)).first() if trip_ref else None
            type_value = str(values["kind"] or "").strip().upper()
            kind = FreightImportRow.Kind.REVENUE if type_value in {"REVENUE", "FREIGHT", "INCOME", "CUSTOMER"} else FreightImportRow.Kind.EXPENSE if type_value in {"EXPENSE", "COST", "FUEL", "TOLL", "DRIVER"} else ""
            try:
                amount = Decimal(str(values["amount"]).replace(",", "")) if values["amount"] is not None else None
                if amount is not None and (not amount.is_finite() or amount <= 0): amount = None
            except Exception:
                amount = None
            date_value = None
            if values["date"]:
                try: date_value = values["date"].date() if hasattr(values["date"], "date") else date.fromisoformat(str(values["date"])[:10])
                except (ValueError, TypeError): pass
            category_text = str(values["category"] or type_value or "OTHER").strip().upper().replace(" ", "_")
            category_aliases = {"FUEL": "FUEL", "DIESEL": "FUEL", "TOLL": "TOLL", "FASTAG": "TOLL", "REPAIR": "REPAIR", "MAINTENANCE": "REPAIR", "PARKING": "PARKING", "LOADING": "LOADING", "ALLOWANCE": "ALLOWANCE", "PERMIT": "PERMIT", "COMMISSION": "COMMISSION"}
            category = category_aliases.get(category_text, "OTHER")
            quantity = None
            try:
                quantity = Decimal(str(values["litres"]).replace(",", "")) if values["litres"] is not None else None
                if quantity is not None and (not quantity.is_finite() or quantity <= 0): quantity = None
            except Exception: pass
            if not trip_ref: note = "Trip reference is missing."
            elif not trip: note = "Trip reference did not match a trip in this workspace."
            elif not kind: note = "Set the row type to REVENUE or EXPENSE."
            elif amount is None: note = "Amount is missing or invalid."
            row = FreightImportRow.objects.create(tenant=request.tenant, batch=batch, row_number=number,
                raw_data=raw_data, trip=trip, kind=kind, category=category,
                description=str(values["description"] or "Imported freight entry")[:200], amount=amount,
                quantity_litres=quantity, incurred_at=date_value, review_note=note)
            created.append(row)
        audit(request, "FREIGHT_FILE_IMPORTED", batch, {"filename": filename, "row_count": len(created), "checksum": digest})
        return Response({"batch_id": str(batch.id), "status": batch.status, "duplicate_upload": False, "rows": [freight_import_row_data(row) for row in created]}, status=201)


class FreightImportRowAction(APIView):
    permission_classes = [HasTenantMembership]

    @transaction.atomic
    def post(self, request, row_id, action):
        if request.membership.role not in EDIT_ROLES | REVIEW_ROLES:
            return Response({"error": "Freight reconciliation access required."}, status=403)
        row = FreightImportRow.objects.select_for_update().select_related("batch", "trip").filter(tenant=request.tenant, id=row_id).first()
        if not row: return Response({"error": "Imported freight row not found."}, status=404)
        if row.status != FreightImportRow.Status.NEEDS_REVIEW:
            return Response({"error": "This row has already been reconciled or ignored."}, status=409)
        if action == "ignore":
            row.status = FreightImportRow.Status.IGNORED
            row.review_note = str(request.data.get("note", "Ignored during review."))[:300]
            row.save(update_fields=["status", "review_note"])
        elif action == "reconcile":
            if request.data.keys() - {"trip_id", "kind", "category", "description", "amount", "quantity_litres", "incurred_at"}:
                return Response({"error": "Unsupported row field."}, status=400)
            trip_id = request.data.get("trip_id")
            if trip_id:
                try: UUID(str(trip_id))
                except ValueError: return Response({"error": "Choose a valid trip."}, status=400)
                row.trip = FleetTrip.objects.filter(tenant=request.tenant, id=trip_id).first()
            kind = request.data.get("kind", row.kind)
            if kind not in FreightImportRow.Kind.values: return Response({"error": "Choose REVENUE or EXPENSE."}, status=400)
            try:
                amount = Decimal(str(request.data.get("amount", row.amount)))
                if not amount.is_finite() or amount <= 0: raise ValueError()
            except Exception: return Response({"error": "Amount must be greater than zero."}, status=400)
            if not row.trip: return Response({"error": "Match this row to a workspace trip before reconciling."}, status=400)
            row.kind = kind; row.amount = amount
            row.description = str(request.data.get("description", row.description or "Imported freight entry"))[:200]
            row.category = str(request.data.get("category", row.category or "OTHER")).upper()
            quantity_value = request.data.get("quantity_litres")
            if quantity_value not in (None, ""):
                try:
                    quantity = Decimal(str(quantity_value))
                    if not quantity.is_finite() or quantity <= 0: raise ValueError()
                    row.quantity_litres = quantity
                except Exception:
                    return Response({"error": "Fuel litres must be a positive number."}, status=400)
            date_value = request.data.get("incurred_at")
            if date_value:
                try: row.incurred_at = date.fromisoformat(str(date_value))
                except ValueError: return Response({"error": "Date must use YYYY-MM-DD."}, status=400)
            if kind == FreightImportRow.Kind.REVENUE:
                revenue = TripRevenueLine.objects.create(tenant=request.tenant, trip=row.trip, description=row.description, amount=amount, is_estimated=False, status=TripRevenueLine.ReviewStatus.DRAFT)
                row.created_revenue = revenue
            else:
                expense = TripExpenseLine.objects.create(tenant=request.tenant, trip=row.trip, category=row.category if row.category in TripExpenseLine.Category.values else TripExpenseLine.Category.OTHER,
                    description=row.description, amount=amount, quantity_litres=row.quantity_litres, incurred_at=row.incurred_at,
                    is_estimated=False, status=TripExpenseLine.ReviewStatus.DRAFT, created_by=request.user)
                row.created_expense = expense
            row.status = FreightImportRow.Status.RECONCILED
            row.reconciled_at = timezone.now(); row.review_note = "Created as a draft trip ledger item; approval is still required."
            row.save()
        else:
            return Response({"error": "Action must be reconcile or ignore."}, status=404)
        has_pending = row.batch.rows.filter(status=FreightImportRow.Status.NEEDS_REVIEW).exists()
        has_completed = row.batch.rows.exclude(status=FreightImportRow.Status.NEEDS_REVIEW).exists()
        row.batch.status = FreightImportBatch.Status.PARTIAL if has_pending and has_completed else FreightImportBatch.Status.REVIEW if has_pending else FreightImportBatch.Status.COMPLETED
        row.batch.save(update_fields=["status"])
        audit(request, f"FREIGHT_IMPORT_ROW_{action.upper()}", row, {"batch_id": str(row.batch_id), "trip_id": str(row.trip_id) if row.trip_id else None, "kind": row.kind, "amount": str(row.amount) if row.amount is not None else None})
        return Response(freight_import_row_data(row))


class ReturnLoadSuggestions(APIView):
    """Suggest reviewable backhauls from delivered trucks to open loads.

    Matching is intentionally exact on normalized place names until a routing
    provider/geocoder is selected; this endpoint never assigns a vehicle.
    """
    permission_classes = [HasTenantMembership]

    def get(self, request):
        if request.membership.role not in EDIT_ROLES | REVIEW_ROLES:
            return Response({"error": "Fleet dispatch access required."}, status=403)
        tenant = request.tenant
        busy_trips = FleetTrip.objects.filter(tenant=tenant, status__in=[
            FleetTrip.Status.DRAFT, FleetTrip.Status.IN_PROGRESS, FleetTrip.Status.SUBMITTED,
        ])
        busy_vehicle_ids = set(busy_trips.values_list("vehicle_id", flat=True))
        busy_driver_ids = set(busy_trips.values_list("driver_id", flat=True))
        open_orders = list(TransportOrder.objects.filter(
            tenant=tenant, status=TransportOrder.Status.OPEN,
        ).select_related("customer").order_by("pickup_due_at", "created_at")[:500])
        completed = FleetTrip.objects.filter(
            tenant=tenant,
            status__in=[FleetTrip.Status.COMPLETED, FleetTrip.Status.SUBMITTED, FleetTrip.Status.APPROVED],
            delivery_at__isnull=False,
            transport_order__status=TransportOrder.Status.DELIVERED,
            vehicle__status=FleetVehicle.Status.ACTIVE,
            driver__status=FleetDriver.Status.ACTIVE,
        ).exclude(vehicle_id__in=busy_vehicle_ids).exclude(driver_id__in=busy_driver_ids).select_related(
            "vehicle", "driver", "transport_order",
        ).order_by("-delivery_at")[:300]
        lane_history = {}
        profitability_history = {}
        historical_trips = list(FleetTrip.objects.filter(tenant=tenant, status__in=[FleetTrip.Status.COMPLETED, FleetTrip.Status.SUBMITTED, FleetTrip.Status.APPROVED], delivery_at__isnull=False).exclude(origin="").exclude(destination="").order_by("-delivery_at")[:2500].only("id", "origin", "destination", "loaded_at", "pickup_at", "starts_at", "delivery_at", "odometer_start", "odometer_end"))
        expense_totals = {row["trip_id"]: row["total"] for row in TripExpenseLine.objects.filter(
            tenant=tenant, trip_id__in=[past.id for past in historical_trips],
            status=TripExpenseLine.ReviewStatus.APPROVED, is_estimated=False,
        ).values("trip_id").annotate(total=Sum("amount"))}
        for past in historical_trips:
            started = past.loaded_at or past.pickup_at or past.starts_at
            if started and past.delivery_at and past.delivery_at > started:
                lane_history.setdefault((normalize_location(past.origin), normalize_location(past.destination)), []).append((past.delivery_at - started).total_seconds())
            if past.odometer_start is not None and past.odometer_end is not None and past.odometer_end > past.odometer_start and past.id in expense_totals:
                lane = (normalize_location(past.origin), normalize_location(past.destination))
                distance = past.odometer_end - past.odometer_start
                cost = expense_totals[past.id]
                profitability_history.setdefault(lane, []).append((distance, cost, cost / distance))

        controls = tenant.settings.get("fleet_controls", {})
        try:
            low_margin_pct = Decimal(str(controls.get("low_margin_percent", "5")))
        except (ValueError, TypeError, ArithmeticError):
            low_margin_pct = Decimal("5")

        suggestions = []
        for trip in completed:
            last_stop = trip.destination or (trip.transport_order.destination if trip.transport_order_id else "")
            location_key = normalize_location(last_stop)
            if not location_key:
                continue
            candidate_orders = [(order, location_match_score(last_stop, order.origin)) for order in open_orders]
            for order, place_score in candidate_orders:
                if place_score < 0.88:
                    continue
                if order.pickup_due_at and trip.delivery_at and order.pickup_due_at < trip.delivery_at:
                    continue
                fit,fit_reason=load_compatibility(trip.vehicle,order)
                if fit is False:
                    continue
                warnings = []
                if fit is None:warnings.append(fit_reason)
                if order.pickup_due_at is None:
                    warnings.append("Pickup time is not set; confirm availability with the customer.")
                if place_score < 1:
                    warnings.append("Pickup location is a fuzzy text match; confirm the actual site before dispatch.")
                idle_minutes = max(0, int((order.pickup_due_at - trip.delivery_at).total_seconds() // 60)) if order.pickup_due_at else None
                if idle_minutes is not None and idle_minutes > 24 * 60:
                    warnings.append("Pickup is more than one day after delivery; confirm the truck and driver remain available.")
                lane_key = (normalize_location(order.origin), normalize_location(order.destination))
                durations = lane_history.get(lane_key, [])
                cost_samples = profitability_history.get(lane_key, [])
                estimated_arrival = None
                if order.pickup_due_at and len(durations) >= 3:
                    estimated_arrival = (order.pickup_due_at + timedelta(seconds=statistics.median(durations))).isoformat()
                profitability = {"status": "INSUFFICIENT_HISTORY", "sample_count": len(cost_samples),
                    "historical_cost_per_km": None, "historical_distance_km": None,
                    "estimated_cost": None, "estimated_profit": None, "estimated_margin_percent": None,
                    "basis": "Requires at least three same-lane completed trips with odometer readings and approved expenses."}
                if len(cost_samples) >= 3:
                    sorted_costs = sorted(sample[2] for sample in cost_samples)
                    sorted_distances = sorted(sample[0] for sample in cost_samples)
                    median_cost_per_km = sorted_costs[len(sorted_costs) // 2] if len(sorted_costs) % 2 else (sorted_costs[len(sorted_costs) // 2 - 1] + sorted_costs[len(sorted_costs) // 2]) / 2
                    median_distance = sorted_distances[len(sorted_distances) // 2] if len(sorted_distances) % 2 else (sorted_distances[len(sorted_distances) // 2 - 1] + sorted_distances[len(sorted_distances) // 2]) / 2
                    estimated_cost = (median_cost_per_km * median_distance).quantize(Decimal("0.01"))
                    amount = order.agreed_amount
                    estimated_profit = (amount - estimated_cost).quantize(Decimal("0.01")) if amount is not None else None
                    margin_pct = (estimated_profit / amount * Decimal("100")).quantize(Decimal("0.01")) if amount and estimated_profit is not None else None
                    profitability = {"status": "ESTIMATED", "sample_count": len(cost_samples),
                        "historical_cost_per_km": str(median_cost_per_km.quantize(Decimal("0.01"))),
                        "historical_distance_km": str(median_distance.quantize(Decimal("0.01"))),
                        "estimated_cost": str(estimated_cost), "estimated_profit": str(estimated_profit) if estimated_profit is not None else None,
                        "estimated_margin_percent": str(margin_pct) if margin_pct is not None else None,
                        "basis": "Historical same-lane median of approved actual trip expenses per kilometre and recorded distance. Estimate only; excludes unrecorded costs."}
                    if margin_pct is not None and margin_pct < low_margin_pct:
                        warnings.append(f"Estimated margin is {margin_pct}% below the workspace alert threshold of {low_margin_pct}%.")
                elif order.agreed_amount is None:
                    warnings.append("No agreed freight rate is recorded, so profitability cannot be estimated.")
                suggestions.append({
                    "id": f"{trip.id}:{order.id}",
                    "source_trip": {"id": str(trip.id), "trip_number": trip.trip_number,
                        "delivered_at": trip.delivery_at.isoformat(), "origin": trip.origin,
                        "destination": last_stop, "vehicle_id": str(trip.vehicle_id),
                        "vehicle": trip.vehicle.registration_number, "capacity": str(trip.vehicle.capacity) if trip.vehicle.capacity is not None else None,
                        "driver_id": str(trip.driver_id), "driver": trip.driver.name},
                    "order": {"id": str(order.id), "order_number": order.order_number,
                        "customer": order.customer.name, "origin": order.origin, "destination": order.destination,
                        "pickup_due_at": order.pickup_due_at.isoformat() if order.pickup_due_at else None,
                        "load_quantity": str(order.load_quantity) if order.load_quantity is not None else None,
                        "load_unit": order.load_unit, "agreed_amount": str(order.agreed_amount) if order.agreed_amount is not None else None},
                    "match_reason": "Open load origin matches the truck's last delivery location; vehicle and driver have no active trip.",
                    "location_match_score": round(place_score, 3),
                    "availability_gap_minutes": idle_minutes,
                    "historical_lane": {"sample_count": len(durations), "median_travel_minutes": int(statistics.median(durations) // 60) if len(durations) >= 3 else None,
                        "estimated_arrival_at": estimated_arrival},
                    "profitability": profitability,
                    "warnings": warnings,
                    "dispatch_url": "/fleet/dispatch",
                })
        suggestions.sort(key=lambda item: (
            -item["location_match_score"],
            item["availability_gap_minutes"] is None,
            item["availability_gap_minutes"] if item["availability_gap_minutes"] is not None else 10**12,
            len(item["warnings"]),
            -(Decimal(item["order"]["agreed_amount"]) if item["order"]["agreed_amount"] else Decimal("0")),
        ))
        trip_ids = [item["source_trip"]["id"] for item in suggestions]
        order_ids = [item["order"]["id"] for item in suggestions]
        offers = ReturnLoadOffer.objects.filter(tenant=tenant, source_trip_id__in=trip_ids, order_id__in=order_ids).select_related("trip").order_by("created_at")
        offers_by_pair = {(str(offer.source_trip_id), str(offer.order_id)): offer for offer in offers}
        for item in suggestions:
            offer = offers_by_pair.get((item["source_trip"]["id"], item["order"]["id"]))
            item["offer"] = {"id": str(offer.id), "status": offer.status, "proposed_amount": str(offer.proposed_amount),
                "accepted_amount": str(offer.accepted_amount) if offer.accepted_amount is not None else None,
                "notes": offer.notes, "booked_trip_id": str(offer.trip_id) if offer.trip_id else None} if offer else None
        return Response({
            "count": len(suggestions), "suggestions": suggestions[:500],
            "matching_method": "normalized exact delivery-to-pickup location, active trip availability, configured capacity, pickup gap, and historical lane travel time",
            "automatically_assigned": False,
            "limitations": ["No live map, road distance, traffic or driver-hours provider is configured; lane time is a historical median when at least three completed trips exist.", "Capacity units are not normalized across trucks and orders. Confirm route, legal load limits and driver hours before assignment."],
        })


class ReturnLoadOfferAction(APIView):
    permission_classes = [HasTenantMembership]

    @transaction.atomic
    def post(self, request, source_trip_id, order_id, action):
        if action not in {"offer", "decline", "confirm"}:
            return Response({"error": "Unknown return-load action."}, status=404)
        if action == "offer" and request.membership.role not in EDIT_ROLES:
            return Response({"error": "Fleet edit permission required to record an offer."}, status=403)
        if action in {"decline", "confirm"} and request.membership.role not in EDIT_ROLES | REVIEW_ROLES:
            return Response({"error": "Fleet review permission required."}, status=403)
        allowed = {"proposed_amount", "notes"} if action == "offer" else {"customer_accepted", "suitability_confirmed", "accepted_amount", "notes"} if action == "confirm" else {"notes"}
        if set(request.data) - allowed:
            return Response({"error": "Unsupported return-load action fields."}, status=400)

        order = TransportOrder.objects.select_for_update().filter(tenant=request.tenant, id=order_id).first()
        source = FleetTrip.objects.select_for_update().select_related("vehicle", "driver").filter(
            tenant=request.tenant, id=source_trip_id).first()
        if not order or not source:
            return Response({"error": "The source trip or open order was not found in this workspace."}, status=404)
        offer = ReturnLoadOffer.objects.select_for_update().filter(
            tenant=request.tenant, source_trip=source, order=order).exclude(status="CANCELLED").first()

        if action == "offer":
            if order.status != TransportOrder.Status.OPEN or source.delivery_at is None or source.status not in {
                FleetTrip.Status.COMPLETED, FleetTrip.Status.SUBMITTED, FleetTrip.Status.APPROVED,
            }:
                return Response({"error": "Only an open order and a completed, delivered source trip can be offered."}, status=409)
            try:
                amount = Decimal(str(request.data.get("proposed_amount", order.agreed_amount or "")))
            except (ValueError, TypeError, ArithmeticError):
                return Response({"error": "Enter a valid proposed freight amount."}, status=400)
            if not amount.is_finite() or amount <= 0 or amount > Decimal("9999999999999999.99") or amount!=amount.quantize(Decimal("0.01")):
                return Response({"error": "Proposed freight amount must be greater than zero and within supported limits."}, status=400)
            if offer and offer.status == ReturnLoadOffer.Status.BOOKED:
                return Response({"error": "This return load is already booked."}, status=409)
            if offer is None:
                offer = ReturnLoadOffer.objects.create(tenant=request.tenant, source_trip=source, order=order,
                    proposed_amount=amount, notes=str(request.data.get("notes", "")).strip()[:500], offered_by=request.user)
            else:
                offer.status = ReturnLoadOffer.Status.OFFERED
                offer.proposed_amount = amount
                offer.notes = str(request.data.get("notes", "")).strip()[:500]
                offer.offered_by = request.user
                offer.accepted_by = None
                offer.accepted_at = None
                offer.accepted_amount = None
                offer.save(update_fields=["status", "proposed_amount", "accepted_amount", "notes", "offered_by", "accepted_by", "accepted_at", "updated_at"])
            audit(request, "RETURN_LOAD_OFFER_RECORDED", offer, {"source_trip_id": str(source.id), "order_id": str(order.id), "proposed_amount": str(amount)})
            return Response({"id": str(offer.id), "status": offer.status, "proposed_amount": str(offer.proposed_amount), "notes": offer.notes}, status=201)

        if not offer:
            return Response({"error": "Record the customer offer before marking it accepted or declined."}, status=409)
        if offer.status == ReturnLoadOffer.Status.BOOKED:
            return Response({"error": "This return load is already booked.", "trip_id": str(offer.trip_id)}, status=409)
        if offer.status != ReturnLoadOffer.Status.OFFERED:
            return Response({"error": "Only a pending offer can be accepted or declined."}, status=409)
        note = str(request.data.get("notes", "")).strip()[:500]
        if action == "decline":
            offer.status = ReturnLoadOffer.Status.DECLINED
            if note:
                offer.notes = note
            offer.save(update_fields=["status", "notes", "updated_at"])
            audit(request, "RETURN_LOAD_OFFER_DECLINED", offer, {"source_trip_id": str(source.id), "order_id": str(order.id), "note": note})
            return Response({"id": str(offer.id), "status": offer.status, "notes": offer.notes})

        if request.data.get("customer_accepted") is not True:
            return Response({"error": "Confirm that the customer accepted this offer before booking the truck."}, status=400)
        if request.data.get("suitability_confirmed") is not True:
            return Response({"error":"Confirm the truck type, capacity units, route restrictions and driver hours before booking."},status=400)
        if order.status != TransportOrder.Status.OPEN or source.delivery_at is None:
            return Response({"error": "The order is no longer open or the source trip is not delivered."}, status=409)
        try:
            accepted_amount = Decimal(str(request.data.get("accepted_amount", offer.proposed_amount)))
        except (ValueError, TypeError, ArithmeticError):
            return Response({"error": "Enter a valid customer-accepted freight amount."}, status=400)
        if not accepted_amount.is_finite() or accepted_amount <= 0 or accepted_amount > Decimal("9999999999999999.99") or accepted_amount!=accepted_amount.quantize(Decimal("0.01")):
            return Response({"error": "Accepted freight amount must be greater than zero and within supported limits."}, status=400)

        vehicle = FleetVehicle.objects.select_for_update().filter(tenant=request.tenant, id=source.vehicle_id, status=FleetVehicle.Status.ACTIVE).first()
        driver = FleetDriver.objects.select_for_update().filter(tenant=request.tenant, id=source.driver_id, status=FleetDriver.Status.ACTIVE).first()
        if not vehicle or not driver:
            return Response({"error": "The truck or driver is no longer active."}, status=409)
        if FleetMaintenanceRecord.objects.filter(tenant=request.tenant,vehicle=vehicle,breakdown_at__isnull=False,returned_to_service_at__isnull=True).exists():
            return Response({"error":"This truck has an open breakdown. Record its return to service before booking."},status=409)
        active_trip_statuses = [FleetTrip.Status.DRAFT, FleetTrip.Status.IN_PROGRESS, FleetTrip.Status.SUBMITTED]
        if FleetTrip.objects.filter(tenant=request.tenant, vehicle=vehicle, status__in=active_trip_statuses).exists():
            return Response({"error": "This truck already has an active trip."}, status=409)
        if FleetTrip.objects.filter(tenant=request.tenant, driver=driver, status__in=active_trip_statuses).exists():
            return Response({"error": "This driver already has an active trip."}, status=409)
        fit,fit_reason=load_compatibility(vehicle,order)
        if fit is False:return Response({"error":fit_reason},status=409)
        if order.load_quantity is not None and vehicle.capacity is None:
            return Response({"error": "Configure the truck capacity before confirming this booking."}, status=409)
        if order.pickup_due_at and order.pickup_due_at < source.delivery_at:
            return Response({"error": "The order pickup window has already passed."}, status=409)
        if location_match_score(source.destination or (source.transport_order.destination if source.transport_order_id else ""), order.origin) < 0.88:
            return Response({"error": "The pickup origin no longer matches the truck's delivery location. Review dispatch manually."}, status=409)

        existing_trip = FleetTrip.objects.filter(tenant=request.tenant, transport_order=order).first()
        if existing_trip:
            return Response({"error": "This order already has a trip assigned.", "trip_id": str(existing_trip.id)}, status=409)
        previous_amount = order.agreed_amount
        if previous_amount != accepted_amount:
            order.agreed_amount = accepted_amount
            order.save(update_fields=["agreed_amount", "updated_at"])
            audit(request, "TRANSPORT_ORDER_RATE_NEGOTIATED", order, {"previous_amount": str(previous_amount) if previous_amount is not None else None,
                "accepted_amount": str(accepted_amount), "offer_id": str(offer.id), "customer_acceptance_recorded_by": str(request.user.id)})
        trip_number = f"RT-{uuid4().hex.upper()}"
        trip = FleetTrip.objects.create(tenant=request.tenant, trip_number=trip_number, vehicle=vehicle, driver=driver,
            transport_order=order, customer_reference=order.customer_reference, origin=order.origin, destination=order.destination,
            starts_at=order.pickup_due_at, status=FleetTrip.Status.DRAFT, created_by=request.user)
        order.status = TransportOrder.Status.ASSIGNED
        order.save(update_fields=["status", "updated_at"])
        offer.status = ReturnLoadOffer.Status.BOOKED
        offer.accepted_amount = accepted_amount
        offer.notes = note or offer.notes
        offer.accepted_by = request.user
        offer.accepted_at = timezone.now()
        offer.trip = trip
        offer.save(update_fields=["status", "accepted_amount", "notes", "accepted_by", "accepted_at", "trip", "updated_at"])
        audit(request, "RETURN_LOAD_BOOKED", offer, {"trip_id": str(trip.id), "source_trip_id": str(source.id),
            "order_id": str(order.id), "vehicle_id": str(vehicle.id), "driver_id": str(driver.id), "accepted_amount": str(accepted_amount)})
        audit(request, "FLEET_TRIP_CREATED", trip, {"source": "RETURN_LOAD_BOOKING", "offer_id": str(offer.id)})
        return Response({"id": str(offer.id), "status": offer.status, "trip_id": str(trip.id),
            "trip_number": trip.trip_number, "order_id": str(order.id), "proposed_amount": str(offer.proposed_amount),
            "accepted_amount": str(accepted_amount)}, status=201)


def dock_appointment_data(row):
    waiting = None
    if row.checked_in_at:
        end=row.checked_out_at or (row.updated_at if row.status in {"CANCELLED","NO_SHOW"} else timezone.now())
        waiting = max(0, int((end - row.checked_in_at).total_seconds() // 60))
    controls = row.tenant.settings.get("fleet_controls", {})
    free_minutes = row.free_minutes_snapshot if row.free_minutes_snapshot is not None else row.order.customer.dock_free_minutes
    if free_minutes is None: free_minutes = int(controls.get("dock_free_minutes", 120))
    detention_rate = row.rate_snapshot if row.rate_snapshot is not None else row.order.customer.detention_rate_per_hour
    if detention_rate is None: detention_rate = Decimal(str(controls.get("detention_rate_per_hour", "0")))
    chargeable_minutes = max(0, (waiting or 0) - free_minutes) if waiting is not None and row.status not in {"CANCELLED","NO_SHOW"} else 0
    detention_estimate = (detention_rate * Decimal(chargeable_minutes) / Decimal(60)).quantize(Decimal("0.01"))
    return {
        "id": str(row.id), "dock_id": str(row.dock_id), "dock_name": row.dock.name,
        "site_name": row.dock.site_name, "order_id": str(row.order_id),
        "order_number": row.order.order_number, "customer": row.order.customer.name,
        "origin": row.order.origin, "destination": row.order.destination,
        "appointment_type": row.appointment_type, "starts_at": row.starts_at.isoformat(),
        "ends_at": row.ends_at.isoformat(), "status": row.status,
        "checked_in_at": row.checked_in_at.isoformat() if row.checked_in_at else None,
        "checked_out_at": row.checked_out_at.isoformat() if row.checked_out_at else None,
        "wait_minutes": waiting, "free_minutes": free_minutes,
        "loading_started_at": row.loading_started_at.isoformat() if row.loading_started_at else None,
        "loading_finished_at": row.loading_finished_at.isoformat() if row.loading_finished_at else None,
        "delay_reason": row.delay_reason, "detention_revenue_id": str(row.detention_revenue_id) if row.detention_revenue_id else None,
        "chargeable_minutes": chargeable_minutes, "detention_rate_per_hour": str(detention_rate),
        "detention_estimate": str(detention_estimate),
        "detention_status": "OVER_FREE_TIME" if chargeable_minutes else "WITHIN_FREE_TIME" if waiting is not None else "NOT_CHECKED_IN",
        "notes": row.notes,
    }


class FleetDocks(APIView):
    permission_classes = [HasTenantMembership]

    def get(self, request):
        if request.membership.role == Membership.Role.DRIVER:
            return Response({"error": "Warehouse scheduling access required."}, status=403)
        rows = FleetDock.objects.filter(tenant=request.tenant, active=True).order_by("site_name", "name")
        return Response([{"id": str(row.id), "site_name": row.site_name, "code": row.code,
            "name": row.name, "parallel_capacity": row.parallel_capacity, "active": row.active} for row in rows])

    def post(self, request):
        if request.membership.role not in EDIT_ROLES:
            return Response({"error": "Fleet edit permission required."}, status=403)
        if set(request.data) != {"site_name", "code", "name", "parallel_capacity"}:
            return Response({"error": "Provide site_name, code, name and parallel_capacity."}, status=400)
        site_name = str(request.data.get("site_name", "")).strip()
        code = str(request.data.get("code", "")).strip().upper()
        name = str(request.data.get("name", "")).strip()
        try:
            capacity = int(request.data.get("parallel_capacity"))
        except (TypeError, ValueError):
            return Response({"error": "Parallel capacity must be a positive whole number."}, status=400)
        if not site_name or len(site_name) > 160 or not code or len(code) > 40 or not name or len(name) > 120 or not 1 <= capacity <= 100:
            return Response({"error": "Enter a valid site, dock code, dock name and capacity from 1 to 100."}, status=400)
        try:
            row = FleetDock.objects.create(tenant=request.tenant, site_name=site_name, code=code, name=name, parallel_capacity=capacity)
        except IntegrityError:
            return Response({"error": "That dock code already exists at this site."}, status=409)
        audit(request, "FLEET_DOCK_CREATED", row, {"site_name": site_name, "code": code, "parallel_capacity": capacity})
        return Response({"id": str(row.id), "site_name": row.site_name, "code": row.code, "name": row.name,
            "parallel_capacity": row.parallel_capacity, "active": row.active}, status=201)


class DockAppointments(APIView):
    permission_classes = [HasTenantMembership]

    def get(self, request):
        if request.membership.role == Membership.Role.DRIVER:
            return Response({"error": "Warehouse scheduling access required."}, status=403)
        rows = DockAppointment.objects.filter(tenant=request.tenant).select_related("tenant", "dock", "order__customer").order_by("starts_at")[:500]
        return Response([dock_appointment_data(row) for row in rows])

    @transaction.atomic
    def post(self, request):
        if request.membership.role not in EDIT_ROLES:
            return Response({"error": "Fleet edit permission required."}, status=403)
        allowed_fields = {"dock_id", "order_id", "appointment_type", "starts_at", "ends_at", "idempotency_key", "notes"}
        required_fields = allowed_fields - {"notes"}
        if set(request.data) - allowed_fields or not required_fields.issubset(request.data):
            return Response({"error": "Provide dock_id, order_id, appointment_type, starts_at, ends_at and idempotency_key."}, status=400)
        try:
            key = UUID(str(request.data["idempotency_key"]))
            dock_id = UUID(str(request.data["dock_id"]))
            order_id = UUID(str(request.data["order_id"]))
        except (TypeError, ValueError, KeyError):
            return Response({"error": "Choose valid workspace dock/order IDs and an idempotency UUID."}, status=400)
        starts_at = parse_datetime(str(request.data.get("starts_at", "")))
        ends_at = parse_datetime(str(request.data.get("ends_at", "")))
        kind = request.data.get("appointment_type")
        if not starts_at or not ends_at or not timezone.is_aware(starts_at) or not timezone.is_aware(ends_at) or ends_at <= starts_at:
            return Response({"error": "Enter valid timezone-aware start and end timestamps; end must follow start."}, status=400)
        if (ends_at - starts_at).total_seconds() > 12 * 60 * 60:
            return Response({"error": "An appointment cannot reserve a dock for more than 12 hours."}, status=400)
        if kind not in DockAppointment.AppointmentType.values:
            return Response({"error": "Choose PICKUP or DELIVERY."}, status=400)
        existing = DockAppointment.objects.filter(tenant=request.tenant, idempotency_key=key).select_related("tenant", "dock", "order__customer").first()
        if existing:
            same = (existing.dock_id == dock_id and existing.order_id == order_id
                and existing.appointment_type == kind and existing.starts_at == starts_at and existing.ends_at == ends_at
                and existing.notes == str(request.data.get("notes", "")).strip()[:500])
            return Response(dock_appointment_data(existing), status=200 if same else 409)
        dock = FleetDock.objects.select_for_update().filter(tenant=request.tenant, id=dock_id, active=True).first()
        if not dock:
            return Response({"error": "Active dock not found in this workspace."}, status=404)
        order = TransportOrder.objects.select_for_update().filter(tenant=request.tenant, id=order_id).select_related("customer").first()
        if not order:
            return Response({"error": "Transport order not found in this workspace."}, status=404)
        eligible = (order.status in {TransportOrder.Status.OPEN, TransportOrder.Status.ASSIGNED}
            if kind == DockAppointment.AppointmentType.PICKUP else order.status == TransportOrder.Status.IN_TRANSIT)
        if not eligible:
            return Response({"error": "Pickup appointments require an open or assigned order; delivery appointments require an in-transit order."}, status=409)
        active_statuses = [DockAppointment.Status.BOOKED, DockAppointment.Status.ARRIVED, DockAppointment.Status.LOADING]
        if DockAppointment.objects.filter(tenant=request.tenant, order=order, appointment_type=kind, status__in=active_statuses).exists():
            return Response({"error": "This order already has an active appointment of this type."}, status=409)
        overlapping = DockAppointment.objects.filter(tenant=request.tenant, dock=dock, status__in=active_statuses,
            starts_at__lt=ends_at, ends_at__gt=starts_at).count()
        if overlapping >= dock.parallel_capacity:
            return Response({"error": "This dock is at capacity during the selected time. Choose another time or dock."}, status=409)
        try:
            row = DockAppointment.objects.create(tenant=request.tenant, dock=dock, order=order,
                appointment_type=kind, starts_at=starts_at, ends_at=ends_at, idempotency_key=key,
                notes=str(request.data.get("notes", "")).strip()[:500], created_by=request.user)
        except IntegrityError:
            return Response({"error": "A conflicting booking or duplicate request was recorded. Refresh the schedule."}, status=409)
        audit(request, "FLEET_DOCK_APPOINTMENT_BOOKED", row, {"order_id": str(order.id), "dock_id": str(dock.id), "starts_at": starts_at.isoformat(), "ends_at": ends_at.isoformat()})
        row = DockAppointment.objects.select_related("tenant", "dock", "order__customer").get(pk=row.pk)
        return Response(dock_appointment_data(row), status=201)


class DockAppointmentAction(APIView):
    permission_classes = [HasTenantMembership]

    @transaction.atomic
    def post(self, request, appointment_id, action):
        if request.membership.role not in EDIT_ROLES | REVIEW_ROLES:
            return Response({"error": "Warehouse scheduling access required."}, status=403)
        if set(request.data) - {"note", "delay_reason"}:
            return Response({"error": "Only a note can be provided for this action."}, status=400)
        row = DockAppointment.objects.select_for_update().select_related("tenant", "dock", "order__customer").filter(tenant=request.tenant, id=appointment_id).first()
        if not row:
            return Response({"error": "Appointment not found."}, status=404)
        transitions = {
            "arrive": (DockAppointment.Status.BOOKED, DockAppointment.Status.ARRIVED),
            "start": (DockAppointment.Status.ARRIVED, DockAppointment.Status.LOADING),
            "complete": (DockAppointment.Status.LOADING, DockAppointment.Status.COMPLETED),
            "cancel": ((DockAppointment.Status.BOOKED, DockAppointment.Status.ARRIVED), DockAppointment.Status.CANCELLED),
        }
        if action not in transitions:
            return Response({"error": "Unknown dock appointment action."}, status=404)
        expected, target = transitions[action]
        allowed_current = expected if isinstance(expected, tuple) else (expected,)
        if row.status not in allowed_current:
            return Response({"error": f"Cannot {action} an appointment in {row.status.lower()} status."}, status=409)
        now = timezone.now()
        if action == "arrive":
            row.checked_in_at = now
            controls = request.tenant.settings.get("fleet_controls", {})
            row.free_minutes_snapshot = row.order.customer.dock_free_minutes if row.order.customer.dock_free_minutes is not None else int(controls.get("dock_free_minutes", 120))
            row.rate_snapshot = row.order.customer.detention_rate_per_hour if row.order.customer.detention_rate_per_hour is not None else Decimal(str(controls.get("detention_rate_per_hour", "0")))
        if action == "start": row.loading_started_at = now
        if action == "complete":
            row.checked_out_at = now
            row.loading_finished_at = row.loading_finished_at or now
        row.status = target
        if "note" in request.data:
            row.notes = str(request.data["note"]).strip()[:500]
        if "delay_reason" in request.data: row.delay_reason = str(request.data["delay_reason"]).strip()[:500]
        row.save()
        audit(request, f"FLEET_DOCK_APPOINTMENT_{target}", row, {"action": action, "note": row.notes})
        return Response(dock_appointment_data(row))


class FleetTripReport(APIView):
    permission_classes = [HasTenantMembership]

    def get(self, request):
        if request.membership.role == Membership.Role.DRIVER:
            return Response({"error": "Fleet report access required."}, status=403)
        tenant = request.tenant
        income = TripRevenueLine.objects.filter(trip_id=OuterRef("pk"), tenant=tenant, status="APPROVED", is_estimated=False).order_by().values("trip_id").annotate(total=Sum("amount")).values("total")[:1]
        costs = TripExpenseLine.objects.filter(trip_id=OuterRef("pk"), tenant=tenant, status="APPROVED", is_estimated=False).order_by().values("trip_id").annotate(total=Sum("amount")).values("total")[:1]
        rows = FleetTrip.objects.filter(tenant=tenant, status=FleetTrip.Status.APPROVED).select_related("vehicle", "driver")
        report_params = request.query_params.copy()
        report_params.pop("status", None)
        rows = filter_trips_from_request(rows, report_params)
        rows = rows.annotate(
            approved_income=Coalesce(Subquery(income, output_field=DecimalField(max_digits=18, decimal_places=2)), Value(Decimal("0.00")), output_field=DecimalField(max_digits=18, decimal_places=2)),
            approved_costs=Coalesce(Subquery(costs, output_field=DecimalField(max_digits=18, decimal_places=2)), Value(Decimal("0.00")), output_field=DecimalField(max_digits=18, decimal_places=2)),
        ).order_by("-starts_at", "-created_at")
        trip_ids = []
        by_driver, by_vehicle, by_month = {}, {}, {}
        total_income = total_costs = Decimal("0.00")
        trip_count = 0
        for trip in rows:
            trip_ids.append(trip.id)
            revenue, expense = trip.approved_income, trip.approved_costs
            total_income += revenue
            total_costs += expense
            trip_count += 1
            month = (trip.starts_at.date() if trip.starts_at else trip.created_at.date()).strftime("%Y-%m")
            group_values = (
                (by_driver, str(trip.driver_id), trip.driver.name),
                (by_vehicle, str(trip.vehicle_id), trip.vehicle.registration_number),
                (by_month, month, month),
            )
            for groups, key, label in group_values:
                row = groups.setdefault(key, {"id": key, "name": label, "trips": 0, "income": Decimal("0.00"), "costs": Decimal("0.00")})
                row["trips"] += 1
                row["income"] += revenue
                row["costs"] += expense

        category_totals = TripExpenseLine.objects.filter(
            tenant=tenant,
            trip_id__in=trip_ids,
            status=TripExpenseLine.ReviewStatus.APPROVED,
            is_estimated=False,
        ).values("category").annotate(
            actual=Sum("amount"),
            budgeted=Sum("budgeted_amount"),
            over_budget=Sum(Case(
                When(budgeted_amount__isnull=False, amount__gt=F("budgeted_amount"), then=F("amount") - F("budgeted_amount")),
                default=Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=18, decimal_places=2),
            )),
            trips=Count("trip_id", distinct=True),
        ).order_by("category")
        category_labels = dict(TripExpenseLine.Category.choices)
        by_cost_category = [{
            "id": row["category"],
            "name": category_labels.get(row["category"], row["category"]),
            "trips": row["trips"],
            "actual": f"{row['actual'] or Decimal('0.00'):.2f}",
            "budgeted": f"{row['budgeted'] or Decimal('0.00'):.2f}",
            "over_budget": f"{row['over_budget'] or Decimal('0.00'):.2f}",
        } for row in category_totals]
        budget_overrun_total = sum((Decimal(row["over_budget"]) for row in by_cost_category), Decimal("0.00"))

        def format_groups(groups):
            return [{**row, "income": f"{row['income']:.2f}", "costs": f"{row['costs']:.2f}", "margin": f"{row['income'] - row['costs']:.2f}"} for row in groups.values()]

        return Response({
            "trip_count": trip_count,
            "income": f"{total_income:.2f}",
            "costs": f"{total_costs:.2f}",
            "margin": f"{total_income - total_costs:.2f}",
            "by_driver": format_groups(by_driver),
            "by_truck": format_groups(by_vehicle),
            "by_month": format_groups(by_month),
            "by_cost_category": by_cost_category,
            "budget_overrun_total": f"{budget_overrun_total:.2f}",
        })


class FleetAlerts(APIView):
    permission_classes = [HasTenantMembership]

    def get(self, request):
        if request.membership.role == Membership.Role.DRIVER:
            return Response({"error": "Fleet manager access required."}, status=403)
        history = {}
        distance_history = {}
        historical_trips = FleetTrip.objects.filter(tenant=request.tenant, status__in=[FleetTrip.Status.COMPLETED, FleetTrip.Status.SUBMITTED, FleetTrip.Status.APPROVED], delivery_at__isnull=False).exclude(origin="").exclude(destination="").order_by("-delivery_at")[:2500]
        for past in historical_trips.only("origin", "destination", "starts_at", "pickup_at", "loaded_at", "delivery_at", "odometer_start", "odometer_end"):
            started = past.loaded_at or past.pickup_at or past.starts_at
            if started and past.delivery_at and past.delivery_at > started:
                route_key = (normalize_location(past.origin), normalize_location(past.destination))
                history.setdefault(route_key, []).append((past.delivery_at - started).total_seconds())
                if past.odometer_start is not None and past.odometer_end is not None and past.odometer_end > past.odometer_start:
                    distance_history.setdefault(route_key, []).append(past.odometer_end - past.odometer_start)
        median_seconds = {key: statistics.median(values) for key, values in history.items() if len(values) >= 3}
        controls = request.tenant.settings.get("fleet_controls", {})
        low_margin_pct = Decimal(str(controls.get("low_margin_percent", "5")))
        duplicate_receipts = set(TripExpenseLine.objects.filter(tenant=request.tenant, receipt__isnull=False,
            is_estimated=False).exclude(status=TripExpenseLine.ReviewStatus.REJECTED).values("receipt__checksum_sha256")
            .annotate(use_count=Count("id")).filter(use_count__gt=1).values_list("receipt__checksum_sha256", flat=True))
        trips = FleetTrip.objects.filter(tenant=request.tenant).exclude(status=FleetTrip.Status.DRAFT).select_related("vehicle", "driver", "transport_order").prefetch_related(
            Prefetch("expense_lines", queryset=TripExpenseLine.objects.select_related("receipt")), "revenue_lines")
        alerts = []
        for trip in trips.iterator(chunk_size=200):
            actual_expenses = [line for line in trip.expense_lines.all() if not line.is_estimated and line.status != TripExpenseLine.ReviewStatus.REJECTED]
            actual_revenue = [line for line in trip.revenue_lines.all() if not line.is_estimated]
            costs = sum((line.amount for line in actual_expenses), Decimal("0"))
            income = sum((line.amount for line in actual_revenue), Decimal("0"))
            for line in actual_expenses:
                if line.budgeted_amount is not None and line.amount > line.budgeted_amount:
                    alerts.append({"id": f"budget:{line.id}", "kind": "BUDGET_OVERRUN", "trip_id": str(trip.id), "trip_number": trip.trip_number, "message": f"{line.category.title()} cost exceeds budget by ₹{line.amount - line.budgeted_amount:.2f}.", "amount": f"{line.amount:.2f}"})
                if line.receipt_id and line.receipt.checksum_sha256 in duplicate_receipts:
                    alerts.append({"id": f"duplicate-receipt:{line.id}", "kind": "DUPLICATE_RECEIPT", "trip_id": str(trip.id), "trip_number": trip.trip_number,
                        "message": f"Receipt {line.receipt.filename} has the same file content as another active trip expense; review both claims.",
                        "receipt_id": str(line.receipt_id), "expense_id": str(line.id), "amount": f"{line.amount:.2f}"})
            if trip.status == FleetTrip.Status.APPROVED and income > 0:
                margin_percent = (income - costs) * Decimal("100") / income
                if margin_percent < low_margin_pct:
                    alerts.append({"id": f"margin:{trip.id}", "kind": "LOW_MARGIN", "trip_id": str(trip.id), "trip_number": trip.trip_number, "message": f"Trip margin is {margin_percent:.1f}%, below the {low_margin_pct}% workspace threshold.", "amount": f"{income - costs:.2f}"})
            delivery_due_at = trip.transport_order.delivery_due_at if trip.transport_order_id else None
            departure = trip.loaded_at or trip.pickup_at or trip.starts_at
            route_key = (normalize_location(trip.origin or (trip.transport_order.origin if trip.transport_order_id else "")), normalize_location(trip.destination or (trip.transport_order.destination if trip.transport_order_id else "")))
            route_median = median_seconds.get(route_key)
            if trip.status == FleetTrip.Status.IN_PROGRESS and departure and route_median:
                estimated_arrival = departure + timedelta(seconds=route_median)
                if delivery_due_at and estimated_arrival > delivery_due_at:
                    minutes_late = max(1, int((estimated_arrival - delivery_due_at).total_seconds() // 60))
                    alerts.append({"id": f"predicted-delay:{trip.id}", "kind": "PREDICTED_DELIVERY_DELAY", "trip_id": str(trip.id), "trip_number": trip.trip_number,
                        "message": f"Based on {len(history[route_key])} previous trips on this route, estimated arrival is about {minutes_late} minute(s) after the scheduled delivery.",
                        "estimated_arrival_at": estimated_arrival.isoformat(), "expected_delivery_at": delivery_due_at.isoformat(), "history_trip_count": len(history[route_key]), "is_open": True, "amount": "0.00"})
            if delivery_due_at and trip.status in (FleetTrip.Status.IN_PROGRESS, FleetTrip.Status.COMPLETED, FleetTrip.Status.SUBMITTED, FleetTrip.Status.APPROVED):
                observed_at = trip.delivery_at or timezone.now()
                delay_seconds = max(0, int((observed_at - delivery_due_at).total_seconds()))
                if delay_seconds:
                    delay_minutes = delay_seconds // 60
                    state = "is still in transit" if trip.delivery_at is None else "was delivered"
                    alerts.append({"id": f"delivery-delay:{trip.id}", "kind": "DELIVERY_DELAY", "trip_id": str(trip.id), "trip_number": trip.trip_number,
                        "message": f"Trip {trip.trip_number} {state} {delay_minutes} minute(s) after its scheduled delivery time.",
                        "delay_minutes": delay_minutes, "expected_delivery_at": delivery_due_at.isoformat(),
                        "actual_delivery_at": trip.delivery_at.isoformat() if trip.delivery_at else None,
                        "is_open": trip.delivery_at is None, "amount": "0.00"})
            controls = request.tenant.settings.get("fleet_controls", {})
            pod_due_hours = max(1, int(controls.get("escalation_hours", 24)))
            if trip.delivery_at and trip.delivery_proof_id is None and not trip.delivery_signature_name.strip() and trip.status in (FleetTrip.Status.COMPLETED, FleetTrip.Status.SUBMITTED, FleetTrip.Status.APPROVED) and timezone.now() - trip.delivery_at >= timedelta(hours=pod_due_hours):
                alerts.append({"id": f"missing-pod:{trip.id}", "kind": "MISSING_DELIVERY_PROOF", "trip_id": str(trip.id), "trip_number": trip.trip_number, "message": f"Trip delivery was recorded without proof or recipient signature more than {pod_due_hours} hour(s) ago.", "amount": "0.00"})
            distance = (trip.odometer_end - trip.odometer_start) if trip.odometer_start is not None and trip.odometer_end is not None else None
            fuel_litres = sum((line.quantity_litres or Decimal("0")) for line in actual_expenses if line.category == TripExpenseLine.Category.FUEL)
            fuel_cost = sum((line.amount for line in actual_expenses if line.category == TripExpenseLine.Category.FUEL), Decimal("0"))
            fuel_price_limit = Decimal(str(controls.get("fuel_price_per_litre_alert", "150")))
            fuel_cost_km_limit = Decimal(str(controls.get("fuel_cost_per_km_alert", "50")))
            if fuel_litres > 0 and fuel_cost / fuel_litres > fuel_price_limit:
                alerts.append({"id": f"fuel-price:{trip.id}", "kind": "FUEL_PRICE_ANOMALY", "trip_id": str(trip.id), "trip_number": trip.trip_number,
                    "message": f"Recorded fuel price is ₹{fuel_cost / fuel_litres:.2f}/L, above the workspace review threshold of ₹{fuel_price_limit:.2f}/L.", "amount": f"{fuel_cost:.2f}"})
            expected = trip.vehicle.expected_km_per_litre
            if distance is not None and distance > 0 and fuel_litres > 0 and expected and distance / fuel_litres < expected:
                efficiency = distance / fuel_litres
                tolerance = Decimal(str(controls.get("fuel_efficiency_tolerance_percent", "20")))
                minimum_efficiency = expected * (Decimal("1") - tolerance / Decimal("100"))
                if efficiency < minimum_efficiency:
                    alerts.append({"id": f"fuel:{trip.id}", "kind": "LOW_FUEL_EFFICIENCY", "trip_id": str(trip.id), "trip_number": trip.trip_number, "message": f"Fuel efficiency was {efficiency:.1f} km/L; the configured alert floor is {minimum_efficiency:.1f} km/L ({tolerance}% tolerance below the {expected} km/L truck baseline).", "amount": f"{efficiency:.2f}"})
            if distance is not None and distance > 0 and trip.status in (FleetTrip.Status.COMPLETED, FleetTrip.Status.SUBMITTED, FleetTrip.Status.APPROVED):
                if fuel_cost_km_limit > 0 and fuel_cost / distance > fuel_cost_km_limit:
                    alerts.append({"id": f"fuel-cost-km:{trip.id}", "kind": "FUEL_COST_PER_KM_ANOMALY", "trip_id": str(trip.id), "trip_number": trip.trip_number,
                        "message": f"Fuel cost is ₹{fuel_cost / distance:.2f}/km, above the workspace review threshold of ₹{fuel_cost_km_limit:.2f}/km.", "amount": f"{fuel_cost / distance:.2f}"})
                route_distances = distance_history.get(route_key, [])
                if len(route_distances) >= 3:
                    median_distance = statistics.median(route_distances)
                    factor = Decimal(str(controls.get("route_distance_anomaly_factor", "2.0")))
                    if Decimal(str(distance)) > Decimal(str(median_distance)) * factor:
                        alerts.append({"id": f"route-distance:{trip.id}", "kind": "ROUTE_DISTANCE_ANOMALY", "trip_id": str(trip.id), "trip_number": trip.trip_number,
                            "message": f"Recorded distance {distance:.1f} km is more than {factor}× the lane median ({median_distance:.1f} km). Check odometer entries or route deviation.",
                            "amount": f"{distance:.2f}", "lane_sample_count": len(route_distances)})
                fuel_lines = [line for line in actual_expenses if line.category == TripExpenseLine.Category.FUEL]
                if not fuel_lines:
                    alerts.append({"id": f"missing-fuel:{trip.id}", "kind": "MISSING_FUEL_RECORD", "trip_id": str(trip.id), "trip_number": trip.trip_number, "message": "Trip has odometer distance but no fuel expense recorded.", "amount": "0.00"})
                elif fuel_litres <= 0:
                    alerts.append({"id": f"missing-litres:{trip.id}", "kind": "MISSING_FUEL_QUANTITY", "trip_id": str(trip.id), "trip_number": trip.trip_number, "message": "Fuel expense recorded without litres, so fuel efficiency cannot be checked.", "amount": "0.00"})
        today = timezone.localdate()
        for document in FleetVehicleDocument.objects.filter(tenant=request.tenant, expires_on__lte=today + timedelta(days=30)).select_related("vehicle"):
            days = (document.expires_on - today).days
            label = "expired" if days < 0 else "expires today" if days == 0 else f"expires in {days} day(s)"
            alerts.append({"id": f"vehicle-document:{document.id}", "kind": "TRUCK_DOCUMENT_EXPIRY", "vehicle_id": str(document.vehicle_id),
                "truck": document.vehicle.registration_number, "message": f"{document.get_kind_display()} for truck {document.vehicle.registration_number} {label}.",
                "expires_on": document.expires_on.isoformat(), "is_open": True, "amount": "0.00"})
        maintenance_rows = FleetMaintenanceRecord.objects.filter(tenant=request.tenant).filter(
            Q(next_due_date__lte=today + timedelta(days=14)) | Q(next_due_odometer_km__isnull=False)
        ).select_related("vehicle").annotate(current_odometer=Max("vehicle__trips__odometer_end"))
        for record in maintenance_rows:
            date_due = record.next_due_date is not None and record.next_due_date <= today + timedelta(days=14)
            distance_due = record.next_due_odometer_km is not None and record.current_odometer is not None and record.current_odometer >= record.next_due_odometer_km
            if not date_due and not distance_due:
                continue
            if distance_due:
                label = f"due at {record.next_due_odometer_km} km (latest recorded odometer: {record.current_odometer} km)"
            else:
                days = (record.next_due_date - today).days
                label = "overdue" if days < 0 else "due today" if days == 0 else f"due in {days} day(s)"
            alerts.append({"id": f"maintenance:{record.id}", "kind": "TRUCK_MAINTENANCE_DUE", "vehicle_id": str(record.vehicle_id),
                "truck": record.vehicle.registration_number, "message": f"{record.description} for truck {record.vehicle.registration_number} is {label}.",
                "next_due_date": record.next_due_date.isoformat() if record.next_due_date else None,
                "next_due_odometer_km": str(record.next_due_odometer_km) if record.next_due_odometer_km else None,
                "is_open": True, "amount": "0.00"})
        return Response({"low_margin_percent": str(low_margin_pct), "alerts": alerts})


class FleetReminderSettings(APIView):
    permission_classes = [HasTenantMembership]
    defaults = {"low_margin_percent": "5", "fuel_efficiency_tolerance_percent": "20",
        "fuel_price_per_litre_alert": "150", "fuel_cost_per_km_alert": "50", "route_distance_anomaly_factor": "2.0",
        "auto_prepare_settlements": True, "recipient_roles": ["OWNER", "FINANCE", "APPROVER"],
        "escalation_hours": 24, "channels": ["IN_APP"],
        "dock_free_minutes": 120, "detention_rate_per_hour": "0", "route_eta_enabled": False}

    def get(self, request):
        values = {**self.defaults, **request.tenant.settings.get("fleet_controls", {})}
        return Response(values)

    def patch(self, request):
        if request.membership.role not in EDIT_ROLES | REVIEW_ROLES:
            return Response({"error": "Fleet settings permission required."}, status=403)
        allowed = set(self.defaults)
        if set(request.data) - allowed:
            return Response({"error": "Unsupported fleet setting."}, status=400)
        current = {**self.defaults, **request.tenant.settings.get("fleet_controls", {})}
        updated = {**current, **request.data}
        try:
            margin = Decimal(str(updated["low_margin_percent"]))
            fuel_tolerance = Decimal(str(updated["fuel_efficiency_tolerance_percent"]))
            fuel_price = Decimal(str(updated["fuel_price_per_litre_alert"]))
            fuel_cost_km = Decimal(str(updated["fuel_cost_per_km_alert"]))
            distance_factor = Decimal(str(updated["route_distance_anomaly_factor"]))
            hours = int(updated["escalation_hours"])
            dock_free_minutes = int(updated["dock_free_minutes"])
            detention_rate = Decimal(str(updated["detention_rate_per_hour"]))
        except (ValueError, TypeError, ArithmeticError):
            return Response({"error": "Enter valid margin and fuel tolerance percentages and an escalation interval."}, status=400)
        valid_roles = set(Membership.Role.values) - {Membership.Role.DRIVER}
        if (not margin.is_finite() or margin < 0 or margin > 100 or not fuel_tolerance.is_finite()
                or fuel_tolerance < 0 or fuel_tolerance > 80 or not fuel_price.is_finite() or not 1 <= fuel_price <= 10000
                or not fuel_cost_km.is_finite() or not 1 <= fuel_cost_km <= 100000
                or not distance_factor.is_finite() or not 1 < distance_factor <= 10 or not 1 <= hours <= 720
                or not 0 <= dock_free_minutes <= 1440 or not detention_rate.is_finite() or not 0 <= detention_rate <= 100000):
            return Response({"error": "Margin must be 0–100%, fuel tolerance 0–80%, fuel price ₹1–₹10,000/L, fuel cost ₹1–₹100,000/km, distance factor >1–10×, and escalation interval 1–720 hours."}, status=400)
        if not isinstance(updated["auto_prepare_settlements"], bool):
            return Response({"error": "auto_prepare_settlements must be true or false."}, status=400)
        if not isinstance(updated["route_eta_enabled"], bool):
            return Response({"error": "route_eta_enabled must be true or false."}, status=400)
        if not isinstance(updated["recipient_roles"], list) or not updated["recipient_roles"] or not set(updated["recipient_roles"]).issubset(valid_roles):
            return Response({"error": "Choose one or more valid notification roles."}, status=400)
        if not isinstance(updated["channels"], list) or not updated["channels"] or not set(updated["channels"]).issubset({"IN_APP", "EMAIL"}):
            return Response({"error": "Choose in-app notifications, email, or both."}, status=400)
        updated["low_margin_percent"] = str(margin)
        updated["fuel_efficiency_tolerance_percent"] = str(fuel_tolerance)
        updated["fuel_price_per_litre_alert"] = str(fuel_price)
        updated["fuel_cost_per_km_alert"] = str(fuel_cost_km)
        updated["route_distance_anomaly_factor"] = str(distance_factor)
        updated["escalation_hours"] = hours
        updated["dock_free_minutes"] = dock_free_minutes
        updated["detention_rate_per_hour"] = str(detention_rate)
        request.tenant.settings = {**request.tenant.settings, "fleet_controls": updated}
        request.tenant.save(update_fields=["settings"])
        audit(request, "FLEET_REMINDER_SETTINGS_UPDATED", request.tenant, updated)
        return Response(updated)


class FleetOperationalReports(APIView):
    permission_classes = [HasTenantMembership]

    def get(self, request, report_name):
        if request.membership.role == Membership.Role.DRIVER:
            return Response({"error": "Operational report access required."}, status=403)
        from exceptions_app.models import InvoiceException
        from payments.models import Payment
        from .models import DriverSalaryRecord
        start, end = request.query_params.get("from"), request.query_params.get("to")
        try:
            start_date = date.fromisoformat(start) if start else None
            end_date = date.fromisoformat(end) if end else None
        except ValueError:
            return Response({"error": "Dates must use YYYY-MM-DD."}, status=400)
        if start_date and end_date and end_date < start_date:
            return Response({"error": "End date must be on or after start date."}, status=400)
        rows = []
        if report_name == "trip-costs":
            qs = FleetTrip.objects.filter(tenant=request.tenant).select_related("driver", "vehicle").prefetch_related("expense_lines")
            if start_date: qs = qs.filter(created_at__date__gte=start_date)
            if end_date: qs = qs.filter(created_at__date__lte=end_date)
            for trip in qs.order_by("-created_at"):
                expenses = [x for x in trip.expense_lines.all() if not x.is_estimated and x.status != TripExpenseLine.ReviewStatus.REJECTED]
                rows.append({"trip_number": trip.trip_number, "date": trip.created_at.date(), "driver": trip.driver.name, "truck": trip.vehicle.registration_number, "status": trip.status, "expense_total": sum((x.amount for x in expenses), Decimal("0.00")), "fuel_litres": sum((x.quantity_litres or Decimal("0")) for x in expenses)})
        elif report_name == "salary-outstanding":
            qs = DriverSalaryRecord.objects.filter(tenant=request.tenant, status__in=[DriverSalaryRecord.Status.APPROVED, DriverSalaryRecord.Status.PARTIALLY_PAID, DriverSalaryRecord.Status.PAID, DriverSalaryRecord.Status.SETTLED]).select_related("driver").prefetch_related("payments", "advance_recoveries")
            if start_date: qs = qs.filter(period_start__gte=start_date)
            if end_date: qs = qs.filter(period_start__lte=end_date)
            for record in qs.order_by("-period_start", "driver__name"):
                paid = sum((x.amount for x in record.payments.all()), Decimal("0"))
                recovered = sum((x.amount for x in record.advance_recoveries.all()), Decimal("0"))
                rows.append({"driver": record.driver.name, "period": record.period_start, "gross_salary": record.salary_amount, "trip_earnings": record.trip_earnings_amount, "gross_earnings": record.gross_earnings_amount, "advance_recovered": recovered, "net_payable": record.gross_earnings_amount - recovered, "paid": paid, "remaining": record.gross_earnings_amount - recovered - paid})
        elif report_name == "invoice-exceptions":
            qs = InvoiceException.objects.filter(tenant=request.tenant).select_related("invoice")
            if start_date: qs = qs.filter(created_at__date__gte=start_date)
            if end_date: qs = qs.filter(created_at__date__lte=end_date)
            rows = [{"invoice": x.invoice.invoice_number or str(x.invoice_id), "code": x.code, "priority": x.priority, "status": x.status, "created_at": x.created_at} for x in qs.order_by("-created_at")]
        elif report_name == "payment-status":
            qs = Payment.objects.filter(tenant=request.tenant).select_related("vendor")
            if start_date: qs = qs.filter(paid_at__gte=start_date)
            if end_date: qs = qs.filter(paid_at__lte=end_date)
            rows = [{"date": x.paid_at, "vendor": x.vendor.name if x.vendor else "", "reference": x.reference_number, "amount": x.amount, "status": "CANCELLED" if x.cancelled_at else "RECORDED"} for x in qs.order_by("-paid_at")]
        else:
            return Response({"error": "Unknown operational report."}, status=404)
        if request.query_params.get("export") == "csv":
            output = io.StringIO()
            columns = list(rows[0]) if rows else ["message"]
            writer = csv.DictWriter(output, fieldnames=columns)
            writer.writeheader()
            for row in rows: writer.writerow({key: str(value) if value is not None else "" for key, value in row.items()})
            response = HttpResponse(output.getvalue(), content_type="text/csv")
            response["Content-Disposition"] = f'attachment; filename="kriyopay-{report_name}.csv"'
            return response
        return Response({"report": report_name, "count": len(rows), "rows": rows})


class TripDetail(APIView):
    permission_classes = [HasTenantMembership]

    def get(self, request, trip_id):
        trip = get_object_or_404(FleetTrip.objects.select_related("vehicle", "driver", "transport_order__customer").prefetch_related("revenue_lines", "expense_lines"), tenant=request.tenant, id=trip_id)
        if request.membership.role == Membership.Role.DRIVER and trip.driver.user_id != request.user.id:
            return Response({"error": "You can only view your assigned trips."}, status=403)
        return Response(FleetTripSerializer(trip, context={"tenant": request.tenant}).data)

    def patch(self, request, trip_id):
        if request.membership.role not in EDIT_ROLES:
            return Response({"error": "Fleet edit permission required"}, status=403)
        trip = get_object_or_404(FleetTrip, tenant=request.tenant, id=trip_id)
        if trip.status not in (FleetTrip.Status.DRAFT, FleetTrip.Status.IN_PROGRESS, FleetTrip.Status.COMPLETED, FleetTrip.Status.REJECTED):
            return Response({"error": "Only draft, in-progress, completed, or rejected trips can be edited."}, status=409)
        serializer = FleetTripSerializer(trip, data=request.data, partial=True, context={"tenant": request.tenant})
        serializer.is_valid(raise_exception=True)
        trip = serializer.save()
        audit(request, "FLEET_TRIP_UPDATED", trip)
        return Response(FleetTripSerializer(trip, context={"tenant": request.tenant}).data)


class TripLines(APIView):
    permission_classes = [HasTenantMembership]

    @transaction.atomic
    def post(self, request, trip_id, kind):
        driver_access = request.membership.role == Membership.Role.DRIVER and kind == "expenses"
        if request.membership.role not in EDIT_ROLES and not driver_access:
            return Response({"error": "Fleet edit permission required"}, status=403)
        trip = get_object_or_404(FleetTrip.objects.select_for_update(), tenant=request.tenant, id=trip_id)
        if driver_access and trip.driver.user_id != request.user.id:
            return Response({"error": "You can only add expenses to your assigned trip."}, status=403)
        if kind == "expenses":
            line_model, serializer_class, action = TripExpenseLine, TripExpenseLineSerializer, "FLEET_TRIP_EXPENSE_CREATED"
            key = request.data.get("idempotency_key")
            if key:
                existing = line_model.objects.filter(tenant=request.tenant, idempotency_key=key).first()
                if existing:
                    if existing.trip_id != trip.id:
                        return Response({"error": "This idempotency key was already used for another trip expense."}, status=409)
                    return Response(serializer_class(existing, context={"tenant": request.tenant}).data, status=200)
        elif kind == "revenue":
            line_model, serializer_class, action = TripRevenueLine, TripRevenueLineSerializer, "FLEET_TRIP_REVENUE_CREATED"
        else:
            return Response({"error": "Unknown trip line type"}, status=404)
        if trip.status not in (FleetTrip.Status.DRAFT, FleetTrip.Status.IN_PROGRESS, FleetTrip.Status.COMPLETED, FleetTrip.Status.REJECTED):
            return Response({"error": "Trip lines cannot be changed after submission."}, status=409)
        serializer = serializer_class(data=request.data, context={"tenant": request.tenant})
        serializer.is_valid(raise_exception=True)
        line = serializer.save(tenant=request.tenant, trip=trip, created_by=request.user) if line_model is TripExpenseLine else serializer.save(tenant=request.tenant, trip=trip)
        audit(request, action, line, {"trip_id": str(trip.id), "amount": str(line.amount)})
        return Response(serializer_class(line, context={"tenant": request.tenant}).data, status=201)

    def delete(self, request, trip_id, kind, line_id):
        if request.membership.role not in EDIT_ROLES:
            return Response({"error": "Fleet edit permission required"}, status=403)
        trip = get_object_or_404(FleetTrip, tenant=request.tenant, id=trip_id)
        if trip.status not in (FleetTrip.Status.DRAFT, FleetTrip.Status.IN_PROGRESS, FleetTrip.Status.COMPLETED, FleetTrip.Status.REJECTED):
            return Response({"error": "Trip lines cannot be removed after submission."}, status=409)
        model = TripExpenseLine if kind == "expenses" else TripRevenueLine if kind == "revenue" else None
        if model is None:
            return Response({"error": "Unknown trip line type"}, status=404)
        line = get_object_or_404(model, tenant=request.tenant, trip=trip, id=line_id)
        audit(request, "FLEET_TRIP_LINE_REMOVED", line, {"trip_id": str(trip.id), "kind": kind, "amount": str(line.amount)})
        line.delete()
        return Response(status=204)


def accrue_driver_trip_earning(trip, request):
    if trip.delivery_at is None:
        return None, "The trip is approved but has no delivery milestone, so no trip earning was accrued."
    trip_date = (trip.delivery_at or trip.ends_at or trip.created_at).date()
    policy = DriverPayPolicy.objects.filter(
        tenant=request.tenant, driver_id=trip.driver_id,
        effective_from__lte=trip_date,
    ).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=trip_date)).order_by("-effective_from").first()
    if policy is None:
        return None, "No effective driver pay policy was found; no trip earning was accrued."
    if policy.basis == DriverPayPolicy.Basis.MONTHLY:
        return None, "The effective pay policy is monthly; this trip is covered by the monthly salary and no separate trip earning was accrued."
    if policy.basis == DriverPayPolicy.Basis.PER_TRIP:
        units = Decimal("1.00")
    else:
        if trip.odometer_start is None or trip.odometer_end is None:
            return None, "The driver pay policy is per kilometre, but this trip has no complete odometer readings. No earning was accrued."
        units = trip.odometer_end - trip.odometer_start
        if units <= 0:
            return None, "Trip distance must be positive for the per-kilometre pay policy. No earning was accrued."
    amount = (policy.rate * units).quantize(Decimal("0.01"))
    earning, created = DriverTripEarning.objects.get_or_create(
        trip=trip,
        defaults={"tenant": request.tenant, "driver_id": trip.driver_id, "policy": policy,
            "basis": policy.basis, "trip_date": trip_date, "units": units,
            "rate_snapshot": policy.rate, "amount": amount},
    )
    salary = DriverSalaryRecord.objects.filter(tenant=request.tenant, driver_id=trip.driver_id,
        period_start__year=trip_date.year, period_start__month=trip_date.month).order_by("-settlement_number").first()
    warning = ""
    if not earning.salary_record_id and salary and salary.status == DriverSalaryRecord.Status.DRAFT:
        earning.salary_record = salary
        earning.save(update_fields=["salary_record"])
    elif not earning.salary_record_id and salary:
        latest_number = DriverSalaryRecord.objects.filter(tenant=request.tenant, driver_id=trip.driver_id, period_start__year=trip_date.year, period_start__month=trip_date.month).aggregate(total=Max("settlement_number"))["total"] or 1
        supplemental = DriverSalaryRecord.objects.create(tenant=request.tenant, driver_id=trip.driver_id,
            period_start=date(trip_date.year, trip_date.month, 1), settlement_number=latest_number + 1,
            salary_amount=Decimal("0.00"), notes="Supplemental settlement for late-approved trip earnings", created_by=request.user)
        earning.salary_record = supplemental
        earning.save(update_fields=["salary_record"])
        audit(request, "FLEET_DRIVER_SUPPLEMENTAL_SETTLEMENT_CREATED", supplemental, {"trip_id": str(trip.id), "trip_earning": str(earning.amount)})
    elif not created:
        warning = "A driver earning was already recorded for this trip."
    return earning, warning


class TripAction(APIView):
    permission_classes = [HasTenantMembership]

    @transaction.atomic
    def post(self, request, trip_id, action):
        trip = get_object_or_404(FleetTrip.objects.select_for_update(of=("self",)).select_related("transport_order"), tenant=request.tenant, id=trip_id)
        if trip.transport_order_id:
            trip.transport_order = get_object_or_404(TransportOrder.objects.select_for_update(), pk=trip.transport_order_id, tenant=request.tenant)
        driver_earning_warning = ""
        is_assigned_driver = request.membership.role == Membership.Role.DRIVER and trip.driver.user_id == request.user.id
        if action == "start":
            if request.membership.role not in EDIT_ROLES and not is_assigned_driver:
                return Response({"error": "Fleet edit permission required"}, status=403)
            if trip.status != FleetTrip.Status.DRAFT:
                if trip.status == FleetTrip.Status.IN_PROGRESS and trip.pickup_at:
                    return Response(FleetTripSerializer(trip, context={"tenant": request.tenant}).data, status=200)
                return Response({"error": "Only a draft trip can be started."}, status=409)
            trip.status = FleetTrip.Status.IN_PROGRESS
            trip.pickup_at = timezone.now()
            if trip.starts_at is None:
                trip.starts_at = timezone.now()
            set_historical_trip_eta(trip, request.tenant)
            odometer_start = request.data.get("odometer_start")
            if odometer_start not in (None, ""):
                try: trip.odometer_start = Decimal(str(odometer_start))
                except Exception: return Response({"error": "Enter a valid starting odometer reading."}, status=400)
                if not trip.odometer_start.is_finite() or trip.odometer_start < 0: return Response({"error": "Starting odometer must be non-negative."}, status=400)
            verb = "FLEET_TRIP_STARTED"
        elif action == "load":
            if request.membership.role not in EDIT_ROLES and not is_assigned_driver:
                return Response({"error": "Fleet edit permission required"}, status=403)
            if trip.loaded_at:
                return Response(FleetTripSerializer(trip, context={"tenant": request.tenant}).data, status=200)
            if trip.status != FleetTrip.Status.IN_PROGRESS:
                return Response({"error": "Check in at pickup before confirming that the load is on the truck."}, status=409)
            trip.loaded_at = timezone.now()
            set_historical_trip_eta(trip, request.tenant)
            verb = "FLEET_TRIP_LOADED"
        elif action == "complete":
            if request.membership.role not in EDIT_ROLES and not is_assigned_driver:
                return Response({"error": "Fleet edit permission required"}, status=403)
            if trip.status != FleetTrip.Status.IN_PROGRESS:
                if trip.status == FleetTrip.Status.COMPLETED and trip.delivery_at:
                    return Response(FleetTripSerializer(trip, context={"tenant": request.tenant}).data, status=200)
                return Response({"error": "Only an in-progress trip can be completed."}, status=409)
            trip.ends_at = timezone.now()
            if trip.starts_at and trip.ends_at <= trip.starts_at:
                return Response({"error": "Trip cannot be completed before its planned start time."}, status=400)
            odometer_end = request.data.get("odometer_end")
            if odometer_end not in (None, ""):
                try:
                    trip.odometer_end = Decimal(str(odometer_end))
                except Exception:
                    return Response({"error": "Enter a valid ending odometer reading."}, status=400)
                if not trip.odometer_end.is_finite() or trip.odometer_end < 0:
                    return Response({"error": "Ending odometer must be a valid non-negative number."}, status=400)
            if trip.odometer_start is not None and trip.odometer_end is not None and trip.odometer_end < trip.odometer_start:
                return Response({"error": "Ending odometer cannot be less than starting odometer."}, status=400)
            trip.status = FleetTrip.Status.COMPLETED
            trip.delivery_at = timezone.now()
            trip.delivery_signature_name = str(request.data.get("delivery_signature_name", "")).strip()[:160]
            proof_id = request.data.get("delivery_proof_id")
            if proof_id:
                trip.delivery_proof = Document.objects.filter(tenant=request.tenant, id=proof_id).first()
                if trip.delivery_proof is None: return Response({"error": "Delivery proof document not found."}, status=400)
            verb = "FLEET_TRIP_COMPLETED"
        elif action == "submit":
            if request.membership.role not in EDIT_ROLES and not is_assigned_driver:
                return Response({"error": "Fleet edit permission required"}, status=403)
            if trip.status not in (FleetTrip.Status.DRAFT, FleetTrip.Status.REJECTED, FleetTrip.Status.IN_PROGRESS, FleetTrip.Status.COMPLETED):
                if trip.status == FleetTrip.Status.SUBMITTED and trip.submitted_by_id == request.user.id:
                    return Response(FleetTripSerializer(trip, context={"tenant": request.tenant}).data, status=200)
                return Response({"error": "Only an editable trip can be submitted."}, status=409)
            trip.status = FleetTrip.Status.SUBMITTED
            trip.submitted_by, trip.submitted_at = request.user, timezone.now()
            trip.review_note = ""
            trip.revenue_lines.update(status=TripRevenueLine.ReviewStatus.SUBMITTED)
            trip.expense_lines.update(status=TripExpenseLine.ReviewStatus.SUBMITTED)
            follow_up_due_at = timezone.now() + timedelta(hours=24)
            for expense in trip.expense_lines.filter(receipt__isnull=True):
                FleetFollowUp.objects.get_or_create(tenant=request.tenant, trip=trip, category="MISSING_RECEIPT", status=FleetFollowUp.Status.OPEN,
                    description=f"Receipt missing for {expense.description} (₹{expense.amount})", defaults={"created_by": request.user, "due_at": follow_up_due_at})
            for expense in trip.expense_lines.filter(budgeted_amount__isnull=False, is_estimated=False):
                if expense.amount > expense.budgeted_amount:
                    variance = expense.amount - expense.budgeted_amount
                    FleetFollowUp.objects.get_or_create(tenant=request.tenant, trip=trip, category="BUDGET_VARIANCE", status=FleetFollowUp.Status.OPEN,
                        description=f"{expense.description} exceeds budget by ₹{variance}", defaults={"created_by": request.user, "due_at": follow_up_due_at})
            verb = "FLEET_TRIP_SUBMITTED"
        elif action in ("approve", "reject"):
            if request.membership.role not in REVIEW_ROLES:
                return Response({"error": "Trip review permission required"}, status=403)
            if trip.status != FleetTrip.Status.SUBMITTED:
                return Response({"error": "Only submitted trips can be reviewed."}, status=409)
            if trip.submitted_by_id == request.user.id:
                return Response({"error": "The trip submitter cannot review their own trip."}, status=403)
            note = str(request.data.get("note", "")).strip()
            if action == "reject" and not note:
                return Response({"error": "A reason is required when rejecting a trip."}, status=400)
            trip.status = FleetTrip.Status.APPROVED if action == "approve" else FleetTrip.Status.REJECTED
            trip.reviewed_by, trip.reviewed_at, trip.review_note = request.user, timezone.now(), note
            line_status = TripRevenueLine.ReviewStatus.APPROVED if action == "approve" else TripRevenueLine.ReviewStatus.DRAFT
            trip.revenue_lines.update(status=line_status)
            trip.expense_lines.update(status=TripExpenseLine.ReviewStatus.APPROVED if action == "approve" else TripExpenseLine.ReviewStatus.REJECTED)
            verb = "FLEET_TRIP_APPROVED" if action == "approve" else "FLEET_TRIP_REJECTED"
            if action == "approve":
                earning, driver_earning_warning = accrue_driver_trip_earning(trip, request)
                if earning:
                    audit(request, "FLEET_DRIVER_TRIP_EARNING_ACCRUED", earning, {"trip_id": str(trip.id), "amount": str(earning.amount), "basis": earning.basis})
        else:
            return Response({"error": "Unknown trip action"}, status=404)
        if trip.transport_order_id:
            order_status = {
                "start": TransportOrder.Status.LOADING,
                "load": TransportOrder.Status.IN_TRANSIT,
                "complete": TransportOrder.Status.DELIVERED,
            }.get(action)
            if order_status:
                order_update = TransportOrder.objects.filter(id=trip.transport_order_id, tenant=request.tenant)
                if action == "start": order_update = order_update.filter(status=TransportOrder.Status.ASSIGNED)
                elif action == "load": order_update = order_update.filter(status=TransportOrder.Status.LOADING)
                order_update.update(status=order_status, updated_at=timezone.now())
        trip.save()
        audit_metadata = {"note": trip.review_note}
        if action in ("approve", "reject"):
            policy_date = (trip.delivery_at or trip.ends_at or trip.created_at).date()
            audit_metadata["pay_policy"] = pay_policy_evidence(request.tenant, trip.driver_id, policy_date)
        audit(request, verb, trip, audit_metadata)
        response_data = FleetTripSerializer(trip, context={"tenant": request.tenant}).data
        if driver_earning_warning:
            response_data["driver_earning_warning"] = driver_earning_warning
        return Response(response_data)


def trip_location_data(trip, location, now=None):
    now = now or timezone.now()
    if not location:
        return {"trip_id": str(trip.id), "trip_number": trip.trip_number, "vehicle": trip.vehicle.registration_number,
            "driver": trip.driver.name, "origin": trip.origin, "destination": trip.destination,
            "status": "WAITING_FOR_GPS", "latitude": None, "longitude": None, "last_seen_at": None}
    age_seconds = max(0, int((now - location.captured_at).total_seconds()))
    return {"trip_id": str(trip.id), "trip_number": trip.trip_number, "vehicle": trip.vehicle.registration_number,
        "driver": trip.driver.name, "origin": trip.origin, "destination": trip.destination,
        "status": "LIVE" if age_seconds <= 120 else "STALE", "latitude": str(location.latitude), "longitude": str(location.longitude),
        "accuracy_m": str(location.accuracy_m) if location.accuracy_m is not None else None,
        "speed_kmh": str(location.speed_kmh) if location.speed_kmh is not None else None,
        "heading_degrees": str(location.heading_degrees) if location.heading_degrees is not None else None,
        "captured_at": location.captured_at.isoformat(), "last_seen_at": location.received_at.isoformat(),
        "age_seconds": age_seconds}


def historical_route_eta_baselines(tenant):
    """Use completed trips as a transparent ETA baseline; no map/traffic provider is implied."""
    cache_key = f"fleet:route-eta-baselines:{tenant.pk}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    durations = {}
    past_trips = FleetTrip.objects.filter(tenant=tenant,
        status__in=[FleetTrip.Status.COMPLETED, FleetTrip.Status.SUBMITTED, FleetTrip.Status.APPROVED],
        delivery_at__isnull=False).select_related("transport_order").order_by("-delivery_at")[:2500]
    for past in past_trips:
        started = past.loaded_at or past.pickup_at or past.starts_at
        delivered = past.delivery_at
        origin = past.origin or (past.transport_order.origin if past.transport_order_id else "")
        destination = past.destination or (past.transport_order.destination if past.transport_order_id else "")
        if started and delivered and delivered > started and origin and destination:
            durations.setdefault((normalize_location(origin), normalize_location(destination)), []).append((delivered - started).total_seconds())
    baselines = {key: {"median_seconds": statistics.median(values), "sample_count": len(values)}
        for key, values in durations.items() if len(values) >= 3}
    cache.set(cache_key, baselines, 300)
    return baselines


def set_historical_trip_eta(trip, tenant):
    origin = trip.origin or (trip.transport_order.origin if trip.transport_order_id else "")
    destination = trip.destination or (trip.transport_order.destination if trip.transport_order_id else "")
    baseline = historical_route_eta_baselines(tenant).get((normalize_location(origin), normalize_location(destination)))
    departure = trip.loaded_at or trip.pickup_at or trip.starts_at
    if baseline and departure:
        trip.predicted_arrival_at = departure + timedelta(seconds=baseline["median_seconds"])
        trip.eta_source = "HISTORICAL_ROUTE_MEDIAN"


class FleetLiveLocations(APIView):
    permission_classes = [HasTenantMembership]

    def get(self, request):
        if request.membership.role not in {Membership.Role.OWNER, Membership.Role.FINANCE, Membership.Role.APPROVER, "FLEET"}:
            return Response({"error": "Fleet live-tracking access required."}, status=403)
        now = timezone.now()
        baselines = historical_route_eta_baselines(request.tenant)
        trips = FleetTrip.objects.filter(tenant=request.tenant, status=FleetTrip.Status.IN_PROGRESS).select_related("vehicle", "driver", "transport_order").prefetch_related(
            Prefetch("latest_phone_location", queryset=FleetTripLocation.objects.all()))[:1000]
        # A OneToOne relation is prefetched to avoid one location query per truck.
        rows = []
        for trip in trips:
            try: location = trip.latest_phone_location
            except FleetTripLocation.DoesNotExist: location = None
            row = trip_location_data(trip, location, now)
            origin = trip.origin or (trip.transport_order.origin if trip.transport_order_id else "")
            destination = trip.destination or (trip.transport_order.destination if trip.transport_order_id else "")
            baseline = baselines.get((normalize_location(origin), normalize_location(destination)))
            departure = trip.loaded_at or trip.pickup_at or trip.starts_at
            if baseline and departure:
                # Remaining time is derived from the historical lane median and elapsed trip time.
                # Until a routing provider and destination coordinates are configured, this is not
                # a GPS-distance or traffic-aware arrival prediction.
                elapsed = max(0, (now - departure).total_seconds())
                remaining = max(0, baseline["median_seconds"] - elapsed)
                eta = (trip.predicted_arrival_at if trip.eta_source != "GOOGLE_TRAFFIC" else None) or now + timedelta(seconds=remaining)
                due_at = trip.transport_order.delivery_due_at if trip.transport_order_id else None
                row.update({"estimated_arrival_at": eta.isoformat(), "eta_method": "HISTORICAL_ROUTE_MEDIAN",
                    "eta_sample_count": baseline["sample_count"],
                    "delivery_at_risk": bool(due_at and eta > due_at),
                    "delivery_due_at": due_at.isoformat() if due_at else None})
            else:
                row.update({"estimated_arrival_at": None, "eta_method": None, "eta_sample_count": 0,
                    "delivery_at_risk": False, "delivery_due_at": None})
            if trip.eta_source == "GOOGLE_TRAFFIC" and trip.route_refreshed_at and now-trip.route_refreshed_at < timedelta(minutes=10) and location and now-location.captured_at < timedelta(minutes=2):
                due_at = trip.transport_order.delivery_due_at if trip.transport_order_id else None
                row.update({"estimated_arrival_at":trip.predicted_arrival_at.isoformat() if trip.predicted_arrival_at else None,
                    "eta_method":"GOOGLE_TRAFFIC","eta_sample_count":0,"delivery_due_at":due_at.isoformat() if due_at else None,
                    "delivery_at_risk":bool(due_at and trip.predicted_arrival_at and trip.predicted_arrival_at>due_at),
                    "route_distance_m":trip.route_distance_m,"route_refreshed_at":trip.route_refreshed_at.isoformat()})
            row["route_error"] = trip.route_error
            rows.append(row)
        return Response({"updated_at": now.isoformat(), "count": len(rows), "trips": rows,
            "refresh_seconds": 15, "stale_after_seconds": 120})


class DriverTripLocation(APIView):
    permission_classes = [HasTenantMembership]

    @transaction.atomic
    def post(self, request, trip_id):
        if request.membership.role != Membership.Role.DRIVER:
            return Response({"error": "Only the assigned driver can report phone GPS for this trip."}, status=403)
        allowed = {"latitude", "longitude", "accuracy_m", "speed_mps", "heading_degrees", "captured_at", "client_event_id"}
        if set(request.data) - allowed or not {"latitude", "longitude", "captured_at", "client_event_id"}.issubset(request.data):
            return Response({"error": "Provide latitude, longitude, captured_at and client_event_id."}, status=400)
        trip = FleetTrip.objects.select_for_update().select_related("driver", "vehicle").filter(
            tenant=request.tenant, id=trip_id, driver__user=request.user).first()
        if not trip:
            return Response({"error": "This trip is not assigned to your driver account."}, status=404)
        if trip.status != FleetTrip.Status.IN_PROGRESS:
            return Response({"error": "Phone GPS is accepted only while the assigned trip is in progress."}, status=409)
        try:
            event_id = UUID(str(request.data["client_event_id"]))
            latitude = Decimal(str(request.data["latitude"]))
            longitude = Decimal(str(request.data["longitude"]))
            captured_at = parse_datetime(str(request.data["captured_at"]))
            accuracy = Decimal(str(request.data["accuracy_m"])) if request.data.get("accuracy_m") not in (None, "") else None
            speed_mps = Decimal(str(request.data["speed_mps"])) if request.data.get("speed_mps") not in (None, "") else None
            heading = Decimal(str(request.data["heading_degrees"])) if request.data.get("heading_degrees") not in (None, "") else None
        except (ValueError, TypeError, ArithmeticError):
            return Response({"error": "GPS values or event ID are invalid."}, status=400)
        if (not latitude.is_finite() or not -90 <= latitude <= 90 or not longitude.is_finite() or not -180 <= longitude <= 180
                or not captured_at or not timezone.is_aware(captured_at)):
            return Response({"error": "Coordinates must be valid latitude/longitude and captured_at must include a timezone."}, status=400)
        now = timezone.now()
        if captured_at > now + timedelta(minutes=2) or captured_at < now - timedelta(minutes=10):
            return Response({"error": "GPS timestamp is outside the accepted 10-minute window. Check the phone's clock and connection."}, status=400)
        if accuracy is not None and (not accuracy.is_finite() or not 0 <= accuracy <= 5000):
            return Response({"error": "GPS accuracy must be between 0 and 5000 metres."}, status=400)
        if speed_mps is not None and (not speed_mps.is_finite() or not 0 <= speed_mps <= 120):
            return Response({"error": "GPS speed is invalid."}, status=400)
        if heading is not None and (not heading.is_finite() or not 0 <= heading < 360):
            return Response({"error": "GPS heading must be between 0 and 359.99 degrees."}, status=400)
        location = FleetTripLocation.objects.select_for_update().filter(tenant=request.tenant, trip=trip).first()
        if location and location.client_event_id == event_id:
            return Response(trip_location_data(trip, location), status=200)
        if location and captured_at <= location.captured_at:
            return Response({**trip_location_data(trip, location), "ignored_stale_update": True}, status=200)
        values = {"reported_by": request.user, "latitude": latitude, "longitude": longitude,
            "accuracy_m": accuracy, "speed_kmh": (speed_mps * Decimal("3.6")) if speed_mps is not None else None,
            "heading_degrees": heading, "captured_at": captured_at, "client_event_id": event_id}
        if location:
            for field, value in values.items(): setattr(location, field, value)
            location.save()
        else:
            try:
                location = FleetTripLocation.objects.create(tenant=request.tenant, trip=trip, **values)
            except IntegrityError:
                return Response({"error": "This GPS update was already submitted."}, status=409)
        from .routing import record_motion
        record_motion(trip, location)
        return Response(trip_location_data(trip, location), status=201)


class MyDriverTrips(APIView):
    permission_classes = [HasTenantMembership]

    def get(self, request):
        if request.membership.role != Membership.Role.DRIVER:
            return Response({"error": "This page is for driver accounts."}, status=403)
        trips = FleetTrip.objects.filter(tenant=request.tenant, driver__user=request.user).select_related("vehicle", "driver", "driver_earning").prefetch_related("expense_lines", "revenue_lines").order_by("-created_at")
        return Response(FleetTripSerializer(trips, many=True, context={"tenant": request.tenant}).data)


class FleetFollowUps(APIView):
    permission_classes = [HasTenantMembership]

    def get(self, request):
        if request.membership.role == Membership.Role.DRIVER:
            return Response({"error": "Fleet follow-up access required."}, status=403)
        qs = FleetFollowUp.objects.filter(tenant=request.tenant).order_by("due_at", "created_at")
        return Response(FleetFollowUpSerializer(qs, many=True).data)

    def post(self, request):
        is_driver = request.membership.role == Membership.Role.DRIVER
        if request.membership.role not in EDIT_ROLES and not is_driver:
            return Response({"error": "Fleet edit permission required"}, status=403)
        data = request.data.copy()
        trip_id = data.get("trip_id")
        if is_driver and not trip_id:
            return Response({"error": "Choose one of your assigned trips."}, status=400)
        if trip_id:
            trip_scope = FleetTrip.objects.filter(tenant=request.tenant)
            if is_driver:
                trip_scope = trip_scope.filter(driver__user=request.user)
            data["trip_id"] = get_object_or_404(trip_scope, id=trip_id).id
        serializer = FleetFollowUpSerializer(data=data, context={"tenant": request.tenant})
        serializer.is_valid(raise_exception=True)
        obj = serializer.save(tenant=request.tenant, created_by=request.user)
        audit(request, "FLEET_FOLLOWUP_CREATED", obj)
        return Response(FleetFollowUpSerializer(obj).data, status=201)

    def patch(self, request, followup_id):
        if request.membership.role not in EDIT_ROLES | REVIEW_ROLES:
            return Response({"error": "Fleet follow-up permission required"}, status=403)
        obj = get_object_or_404(FleetFollowUp, tenant=request.tenant, id=followup_id)
        action = request.data.get("action")
        note = str(request.data.get("note", "")).strip()
        if action not in ("start", "resolve", "waive"):
            return Response({"error": "action must be start, resolve, or waive"}, status=400)
        if action == "waive" and (request.membership.role not in REVIEW_ROLES or not note):
            return Response({"error": "A reviewer and reason are required to waive a follow-up."}, status=403)
        obj.status = {"start": FleetFollowUp.Status.IN_PROGRESS, "resolve": FleetFollowUp.Status.RESOLVED, "waive": FleetFollowUp.Status.WAIVED}[action]
        obj.resolution_note = note
        if action in ("resolve", "waive"):
            obj.resolved_by, obj.resolved_at = request.user, timezone.now()
        obj.save(update_fields=["status", "resolution_note", "resolved_by", "resolved_at"])
        audit(request, {"start": "FLEET_FOLLOWUP_STARTED", "resolve": "FLEET_FOLLOWUP_RESOLVED", "waive": "FLEET_FOLLOWUP_WAIVED"}[action], obj, {"note": note})
        return Response(FleetFollowUpSerializer(obj).data)


def prepare_driver_settlements(tenant, period_start, actor=None):
    """Create idempotent salary drafts from effective policies and approved trip earnings."""
    import json

    next_month = date(period_start.year + (period_start.month == 12), period_start.month % 12 + 1, 1)
    policies = list(DriverPayPolicy.objects.filter(
        tenant=tenant, effective_from__lt=next_month,
    ).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=period_start))
        .select_related("driver").order_by("driver_id", "-effective_from"))
    controls = tenant.settings.get("fleet_controls", {})
    policy_data = [{"driver_id": str(item.driver_id), "basis": item.basis, "rate": str(item.rate),
        "effective_from": item.effective_from.isoformat(), "effective_to": item.effective_to.isoformat() if item.effective_to else None}
        for item in policies]
    policy_version = hashlib.sha256(json.dumps({"policies": policy_data, "fleet_controls": controls}, sort_keys=True).encode()).hexdigest()[:16]
    policies_by_driver = {}
    for policy in policies:
        if policy.effective_from <= period_start and (policy.effective_to is None or policy.effective_to >= period_start):
            policies_by_driver.setdefault(policy.driver_id, policy)

    created, existing, discrepancies, records = 0, 0, [], []
    drivers = FleetDriver.objects.filter(tenant=tenant, status=FleetDriver.Status.ACTIVE).order_by("name")
    for driver in drivers:
        with transaction.atomic():
            FleetDriver.objects.select_for_update().filter(pk=driver.pk, tenant=tenant).exists()
            prior_records = list(DriverSalaryRecord.objects.filter(tenant=tenant, driver=driver,
                period_start=period_start).order_by("-settlement_number"))
            earning_rows = DriverTripEarning.objects.filter(tenant=tenant, driver=driver,
                trip_date__gte=period_start, trip_date__lt=next_month, salary_record__isnull=True)
            earning_total = earning_rows.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
            expense_rows = TripExpenseLine.objects.filter(tenant=tenant, trip__driver=driver,
                trip__status=FleetTrip.Status.APPROVED, status=TripExpenseLine.ReviewStatus.APPROVED,
                paid_by_driver=True, is_estimated=False, driver_settlement__isnull=True).filter(
                    Q(incurred_at__gte=period_start, incurred_at__lt=next_month)
                    | Q(incurred_at__isnull=True, trip__delivery_at__date__gte=period_start,
                        trip__delivery_at__date__lt=next_month))
            policy = policies_by_driver.get(driver.pk)
            monthly_base = policy.rate if not prior_records and policy and policy.basis == DriverPayPolicy.Basis.MONTHLY else Decimal("0.00")
            has_expenses = expense_rows.exists()
            if not policy and earning_total <= 0 and not has_expenses:
                missing_policy_trips = FleetTrip.objects.filter(tenant=tenant, driver=driver,
                    status=FleetTrip.Status.APPROVED, delivery_at__date__gte=period_start,
                    delivery_at__date__lt=next_month).count()
                if missing_policy_trips:
                    discrepancies.append({"driver_id": str(driver.pk), "driver": driver.name,
                        "reason": "Approved trips exist but no effective pay policy was configured."})
                continue
            if monthly_base <= 0 and earning_total <= 0 and not has_expenses:
                if prior_records:
                    existing += 1
                    records.append(str(prior_records[0].pk))
                continue
            reusable_draft = next((item for item in prior_records if item.status == DriverSalaryRecord.Status.DRAFT and not item.payments.exists()), None)
            if reusable_draft:
                record = reusable_draft
                existing += 1
            else:
                record = DriverSalaryRecord.objects.create(tenant=tenant, driver=driver, period_start=period_start,
                    settlement_number=(prior_records[0].settlement_number + 1) if prior_records else 1,
                    salary_amount=monthly_base, status=DriverSalaryRecord.Status.DRAFT,
                    notes=f"Prepared from approved trips and effective pay policy {policy_version}.", created_by=actor)
                created += 1
            earning_rows.update(salary_record=record)
            DriverExpenseSettlement.objects.bulk_create([DriverExpenseSettlement(tenant=tenant,
                salary_record=record, expense=expense, amount=expense.amount) for expense in expense_rows])
            records.append(str(record.pk))
    return {"period": period_start.strftime("%Y-%m"), "created": created, "already_present": existing,
        "discrepancies": discrepancies, "record_ids": records, "policy_version": policy_version,
        "message": "Drafts use approved trip earnings and the effective monthly policy. Approved deductions are reflected in the ledger; advances remain visible for an authorized recovery. Review and approve each draft before recording a payment. No bank transfer was initiated."}


class DriverSalaries(APIView):
    permission_classes = [HasTenantMembership]

    def get(self, request):
        if request.membership.role == Membership.Role.DRIVER:
            return Response({"error": "Salary records are available through your employer."}, status=403)
        records = DriverSalaryRecord.objects.filter(tenant=request.tenant).select_related("driver", "submitted_by", "approved_by").prefetch_related("payments", "trip_earnings", "advance_recoveries").order_by("-period_start", "driver__name", "settlement_number")
        return Response(DriverSalaryRecordSerializer(records, many=True, context={"tenant": request.tenant}).data)

    def post(self, request):
        if request.membership.role not in EDIT_ROLES | REVIEW_ROLES:
            return Response({"error": "Salary editing permission required"}, status=403)
        if request.data.get("action") == "prepare":
            try:
                period_start = date.fromisoformat(f"{request.data.get('period', '')}-01")
            except (TypeError, ValueError):
                return Response({"error": "period must use YYYY-MM format."}, status=400)
            if period_start.day != 1:
                return Response({"error": "period must use YYYY-MM format."}, status=400)
            prepared = prepare_driver_settlements(request.tenant, period_start, request.user)
            audit(request, "FLEET_DRIVER_SETTLEMENTS_PREPARED", request.tenant, {
                "period": period_start.strftime("%Y-%m"),
                "policy_version": prepared["policy_version"],
                "created": prepared["created"],
                "discrepancies": prepared["discrepancies"],
                "money_movement_enabled": False,
            })
            return Response(prepared)
        serializer = DriverSalaryRecordSerializer(data=request.data, context={"tenant": request.tenant})
        serializer.is_valid(raise_exception=True)
        try:
            record = serializer.save(tenant=request.tenant, created_by=request.user)
        except IntegrityError:
            return Response({"error": "A salary record already exists for this driver and month."}, status=409)
        audit(request, "FLEET_DRIVER_SALARY_RECORDED", record, {"salary_amount": str(record.salary_amount), "period_start": str(record.period_start)})
        return Response(DriverSalaryRecordSerializer(record, context={"tenant": request.tenant}).data, status=201)


class DriverSalaryPayments(APIView):
    permission_classes = [HasTenantMembership]

    @transaction.atomic
    def post(self, request, salary_id):
        if request.membership.role not in EDIT_ROLES | REVIEW_ROLES:
            return Response({"error": "Salary payment permission required"}, status=403)
        record = get_object_or_404(DriverSalaryRecord.objects.select_for_update(), tenant=request.tenant, id=salary_id)
        idempotency_key = request.data.get("idempotency_key")
        if idempotency_key:
            existing = DriverSalaryPayment.objects.filter(tenant=request.tenant, idempotency_key=idempotency_key).first()
            if existing:
                if existing.salary_record_id != record.id:
                    return Response({"error": "This idempotency key was already used for another salary payment."}, status=409)
                record = DriverSalaryRecord.objects.select_related("driver").prefetch_related("payments").get(id=record.id)
                return Response(DriverSalaryRecordSerializer(record, context={"tenant": request.tenant}).data, status=200)
        if record.status not in {DriverSalaryRecord.Status.APPROVED, DriverSalaryRecord.Status.PARTIALLY_PAID}:
            return Response({"error": "Submit the salary for review and get it approved before recording a payment."}, status=409)
        serializer = DriverSalaryPaymentSerializer(data=request.data, context={"salary_record": record})
        serializer.is_valid(raise_exception=True)
        payment = serializer.save(tenant=request.tenant, salary_record=record, created_by=request.user)
        paid_total = record.payments.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        recovered_total = record.advance_recoveries.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        deductions = record.adjustments.filter(kind=DriverSalaryAdjustment.Kind.DEDUCTION, status=DriverSalaryAdjustment.Status.APPROVED).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        reversals = record.adjustments.filter(kind=DriverSalaryAdjustment.Kind.PAYMENT_REVERSAL, status=DriverSalaryAdjustment.Status.APPROVED).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        total_settled = paid_total - reversals + recovered_total
        record.status = (DriverSalaryRecord.Status.SETTLED if recovered_total > 0 else DriverSalaryRecord.Status.PAID) if total_settled >= record.gross_earnings_amount - deductions else DriverSalaryRecord.Status.PARTIALLY_PAID
        record.save(update_fields=["status", "updated_at"])
        audit(request, "FLEET_DRIVER_SALARY_PAID", payment, {"salary_record_id": str(record.id), "amount": str(payment.amount)})
        record = DriverSalaryRecord.objects.select_related("driver").prefetch_related("payments").get(id=record.id)
        return Response(DriverSalaryRecordSerializer(record, context={"tenant": request.tenant}).data, status=201)


class DriverSalaryReview(APIView):
    permission_classes = [HasTenantMembership]

    @transaction.atomic
    def post(self, request, salary_id, action):
        record = get_object_or_404(DriverSalaryRecord.objects.select_for_update(), tenant=request.tenant, id=salary_id)
        if action == "submit":
            if request.membership.role not in EDIT_ROLES | REVIEW_ROLES:
                return Response({"error": "Salary submission permission required."}, status=403)
            if record.status != DriverSalaryRecord.Status.DRAFT:
                return Response({"error": "Only draft salary records can be submitted."}, status=409)
            record.status = DriverSalaryRecord.Status.SUBMITTED
            record.submitted_by, record.submitted_at = request.user, timezone.now()
            audit(request, "FLEET_DRIVER_SALARY_SUBMITTED", record, {"salary_amount": str(record.salary_amount), "period_start": str(record.period_start), "pay_policy": pay_policy_evidence(request.tenant, record.driver_id, record.period_start)})
        elif action == "approve":
            if request.membership.role not in REVIEW_ROLES:
                return Response({"error": "Salary review permission required."}, status=403)
            if record.status != DriverSalaryRecord.Status.SUBMITTED:
                return Response({"error": "Only submitted salary records can be approved."}, status=409)
            if record.submitted_by_id == request.user.id:
                return Response({"error": "The person who submitted the salary cannot approve it. Ask another finance reviewer."}, status=403)
            record.status = DriverSalaryRecord.Status.APPROVED
            record.approved_by, record.approved_at = request.user, timezone.now()
            audit(request, "FLEET_DRIVER_SALARY_APPROVED", record, {"salary_amount": str(record.salary_amount), "period_start": str(record.period_start), "pay_policy": pay_policy_evidence(request.tenant, record.driver_id, record.period_start)})
        elif action == "reject":
            if request.membership.role not in REVIEW_ROLES:
                return Response({"error": "Salary review permission required."}, status=403)
            if record.status != DriverSalaryRecord.Status.SUBMITTED:
                return Response({"error": "Only submitted salary records can be returned for changes."}, status=409)
            note = str(request.data.get("note", "")).strip()
            if not note:
                return Response({"error": "A reason is required when returning a salary record."}, status=400)
            record.status = DriverSalaryRecord.Status.DRAFT
            record.review_note = note[:240]
            record.submitted_by, record.submitted_at = None, None
            audit(request, "FLEET_DRIVER_SALARY_RETURNED", record, {"note": record.review_note, "salary_amount": str(record.salary_amount)})
        else:
            return Response({"error": "Unknown salary review action."}, status=404)
        record.save(update_fields=["status", "submitted_by", "submitted_at", "approved_by", "approved_at", "review_note", "updated_at"])
        record = DriverSalaryRecord.objects.select_related("driver", "submitted_by", "approved_by").prefetch_related("payments").get(id=record.id)
        return Response(DriverSalaryRecordSerializer(record, context={"tenant": request.tenant}).data)


class DriverSalaryDetail(APIView):
    permission_classes = [HasTenantMembership]

    @transaction.atomic
    def patch(self, request, salary_id):
        if request.membership.role not in EDIT_ROLES | REVIEW_ROLES:
            return Response({"error": "Salary editing permission required."}, status=403)
        record = get_object_or_404(DriverSalaryRecord.objects.select_for_update(), tenant=request.tenant, id=salary_id)
        if record.status != DriverSalaryRecord.Status.DRAFT or record.payments.exists():
            return Response({"error": "Only an unpaid draft salary record can be edited."}, status=409)
        serializer = DriverSalaryRecordSerializer(record, data=request.data, partial=True, context={"tenant": request.tenant})
        serializer.is_valid(raise_exception=True)
        try:
            record = serializer.save(review_note="")
        except IntegrityError:
            return Response({"error": "A salary record already exists for this driver and month."}, status=409)
        audit(request, "FLEET_DRIVER_SALARY_UPDATED", record, {"salary_amount": str(record.salary_amount), "period_start": str(record.period_start)})
        record = DriverSalaryRecord.objects.select_related("driver", "submitted_by", "approved_by").prefetch_related("payments").get(id=record.id)
        return Response(DriverSalaryRecordSerializer(record, context={"tenant": request.tenant}).data)


class DriverSalaryAdjustments(APIView):
    permission_classes = [HasTenantMembership]

    @transaction.atomic
    def post(self, request, salary_id):
        if request.membership.role not in EDIT_ROLES | REVIEW_ROLES:
            return Response({"error": "Driver salary adjustment permission required."}, status=403)
        record = get_object_or_404(DriverSalaryRecord.objects.select_for_update(), tenant=request.tenant, id=salary_id)
        if record.status not in {DriverSalaryRecord.Status.APPROVED, DriverSalaryRecord.Status.PARTIALLY_PAID, DriverSalaryRecord.Status.PAID, DriverSalaryRecord.Status.SETTLED}:
            return Response({"error": "Adjustments can be recorded after salary approval."}, status=409)
        key = request.data.get("idempotency_key")
        if key:
            existing = DriverSalaryAdjustment.objects.filter(tenant=request.tenant, idempotency_key=key).first()
            if existing:
                if existing.salary_record_id != record.id or existing.kind != request.data.get("kind") or existing.amount != Decimal(str(request.data.get("amount", "0"))):
                    return Response({"error": "This request key was already used for a different salary adjustment."}, status=409)
                return Response(self._data(existing), status=200)
        serializer = DriverSalaryAdjustmentSerializer(data=request.data, context={"tenant": request.tenant, "salary_record": record})
        serializer.is_valid(raise_exception=True)
        item = serializer.save(tenant=request.tenant, salary_record=record, submitted_by=request.user)
        audit(request, "FLEET_DRIVER_SALARY_ADJUSTMENT_SUBMITTED", item, {"salary_record_id": str(record.id), "kind": item.kind, "amount": str(item.amount), "reason": item.reason})
        return Response(self._data(item), status=201)

    @staticmethod
    def _data(item):
        return {"id": str(item.id), "kind": item.kind, "category": item.category, "amount": f"{item.amount:.2f}", "reason": item.reason, "adjustment_date": item.adjustment_date.isoformat(), "status": item.status, "review_note": item.review_note, "submitted_by_id": item.submitted_by_id, "approved_by_id": item.approved_by_id, "original_payment_id": str(item.original_payment_id) if item.original_payment_id else None, "evidence_id": str(item.evidence_id) if item.evidence_id else None}


class DriverSalaryAdjustmentReview(APIView):
    permission_classes = [HasTenantMembership]

    @transaction.atomic
    def post(self, request, adjustment_id, action):
        if request.membership.role not in REVIEW_ROLES:
            return Response({"error": "Driver salary reviewer permission required."}, status=403)
        item = get_object_or_404(DriverSalaryAdjustment.objects.select_for_update().select_related("salary_record"), tenant=request.tenant, id=adjustment_id)
        if item.status != DriverSalaryAdjustment.Status.SUBMITTED:
            return Response({"error": "Only submitted adjustments can be reviewed."}, status=409)
        if item.submitted_by_id == request.user.id:
            return Response({"error": "The person who submitted this adjustment cannot review it."}, status=403)
        if action not in {"approve", "reject"}:
            return Response({"error": "Unknown adjustment review action."}, status=404)
        note = str(request.data.get("note", "")).strip()
        if action == "reject" and not note:
            return Response({"error": "A reason is required when rejecting an adjustment."}, status=400)
        item.status = DriverSalaryAdjustment.Status.APPROVED if action == "approve" else DriverSalaryAdjustment.Status.REJECTED
        item.approved_by = request.user
        item.reviewed_at = timezone.now()
        item.review_note = note[:240]
        item.save(update_fields=["status", "approved_by", "reviewed_at", "review_note"])
        record = item.salary_record
        paid = record.payments.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        reversed_paid = record.adjustments.filter(kind=DriverSalaryAdjustment.Kind.PAYMENT_REVERSAL, status=DriverSalaryAdjustment.Status.APPROVED).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        recovered = record.advance_recoveries.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        deductions = record.adjustments.filter(kind=DriverSalaryAdjustment.Kind.DEDUCTION, status=DriverSalaryAdjustment.Status.APPROVED).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        payable = record.gross_earnings_amount - deductions
        settled = paid - reversed_paid + recovered
        if action == "approve":
            record.status = DriverSalaryRecord.Status.SETTLED if settled >= payable and recovered else DriverSalaryRecord.Status.PAID if settled >= payable else DriverSalaryRecord.Status.PARTIALLY_PAID
            record.save(update_fields=["status", "updated_at"])
        audit(request, f"FLEET_DRIVER_SALARY_ADJUSTMENT_{action.upper()}D", item, {"salary_record_id": str(record.id), "kind": item.kind, "amount": str(item.amount), "note": note})
        return Response(DriverSalaryAdjustments._data(item))


class DriverLedgerExport(APIView):
    permission_classes = [HasTenantMembership]

    def get(self, request):
        if request.membership.role == Membership.Role.DRIVER:
            return Response({"error": "Driver ledger export permission required."}, status=403)
        try:
            start = date.fromisoformat(request.query_params.get("start_date"))
            end = date.fromisoformat(request.query_params.get("end_date"))
            if end < start:
                raise ValueError
        except (TypeError, ValueError):
            return Response({"error": "Provide a valid start_date and end_date in YYYY-MM-DD format."}, status=400)
        drivers = FleetDriver.objects.filter(tenant=request.tenant)
        if request.query_params.get("driver_id"):
            drivers = drivers.filter(id=request.query_params["driver_id"])
        rows = []
        for driver in drivers.order_by("name"):
            movements = []
            salaries = DriverSalaryRecord.objects.filter(tenant=request.tenant, driver=driver, status__in=[DriverSalaryRecord.Status.APPROVED, DriverSalaryRecord.Status.PARTIALLY_PAID, DriverSalaryRecord.Status.PAID, DriverSalaryRecord.Status.SETTLED]).prefetch_related("payments", "advance_recoveries", "adjustments", "expense_settlements__expense__trip")
            for salary in salaries:
                movements.append((salary.period_start, "Monthly salary", f"Settlement {salary.id}", salary.salary_amount))
                for payment in salary.payments.all(): movements.append((payment.payment_date, "Salary payment", payment.payment_reference, -payment.amount))
                for recovery in salary.advance_recoveries.all(): movements.append((recovery.created_at.date(), "Advance recovery", f"Advance {recovery.advance_id}", Decimal("0.00")))
                for reimbursement in salary.expense_settlements.all():
                    expense = reimbursement.expense
                    movement_date = expense.incurred_at or (expense.trip.delivery_at.date() if expense.trip.delivery_at else salary.period_start)
                    movements.append((movement_date, f"Driver expense reimbursement · {expense.category}", expense.trip.trip_number, reimbursement.amount))
                for adjustment in salary.adjustments.filter(status=DriverSalaryAdjustment.Status.APPROVED):
                    if adjustment.kind == DriverSalaryAdjustment.Kind.DEDUCTION: movements.append((adjustment.adjustment_date, "Approved deduction", f"{adjustment.category}: {adjustment.reason}", -adjustment.amount))
                    else: movements.append((adjustment.adjustment_date, "Payment reversal", adjustment.reason, adjustment.amount))
            eligible_earnings = DriverTripEarning.objects.filter(tenant=request.tenant, driver=driver).filter(Q(salary_record__isnull=True) | Q(salary_record__status__in=[DriverSalaryRecord.Status.APPROVED, DriverSalaryRecord.Status.PARTIALLY_PAID, DriverSalaryRecord.Status.PAID, DriverSalaryRecord.Status.SETTLED])).select_related("trip")
            for earning in eligible_earnings: movements.append((earning.trip_date, "Trip earning", earning.trip.trip_number, earning.amount))
            for advance in DriverAdvance.objects.filter(tenant=request.tenant, driver=driver): movements.append((advance.given_date, "Driver advance", advance.reference or advance.notes, -advance.amount))
            movements.sort(key=lambda item: (item[0], item[1]))
            opening = sum((amount for movement_date, _, _, amount in movements if movement_date < start), Decimal("0.00"))
            running = opening
            selected = [movement for movement in movements if start <= movement[0] <= end]
            if not selected:
                rows.append((driver.name, "", "Opening/closing balance", "", opening, Decimal("0.00"), opening))
            for movement_date, kind, reference, amount in selected:
                before = running
                running += amount
                rows.append((driver.name, movement_date.isoformat(), kind, reference, before, amount, running))
            if selected:
                rows.append((driver.name, "", "Closing balance", "", opening, Decimal("0.00"), running))
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="driver-ledger-{start.isoformat()}-to-{end.isoformat()}.csv"'
        writer = csv.writer(response)
        writer.writerow(["Driver", "Date", "Entry", "Reference", "Balance before", "Change", "Balance after"])
        for row in rows: writer.writerow([*row[:4], f"{row[4]:.2f}", f"{row[5]:.2f}", f"{row[6]:.2f}"])
        return response


def driver_advance_data(advance):
    recovered = advance.recoveries.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    return {
        "id": str(advance.id), "driver": {"id": str(advance.driver_id), "name": advance.driver.name},
        "amount": f"{advance.amount:.2f}", "recovered_amount": f"{recovered:.2f}",
        "outstanding_amount": f"{max(advance.amount - recovered, Decimal('0.00')):.2f}",
        "status": advance.status, "given_date": advance.given_date.isoformat(),
        "reference": advance.reference, "notes": advance.notes,
        "recoveries": [{"id": str(item.id), "amount": f"{item.amount:.2f}", "period_start": item.salary_record.period_start.isoformat(), "created_at": item.created_at.isoformat()} for item in advance.recoveries.select_related("salary_record").order_by("-created_at")],
    }


class DriverAdvances(APIView):
    permission_classes = [HasTenantMembership]

    def get(self, request):
        if request.membership.role == Membership.Role.DRIVER:
            return Response({"error": "Driver finance access required."}, status=403)
        rows = DriverAdvance.objects.filter(tenant=request.tenant).select_related("driver").prefetch_related("recoveries__salary_record").order_by("-given_date", "-created_at")
        return Response([driver_advance_data(row) for row in rows])

    @transaction.atomic
    def post(self, request):
        if request.membership.role not in EDIT_ROLES | REVIEW_ROLES:
            return Response({"error": "Driver advance permission required."}, status=403)
        serializer = DriverAdvanceCreateSerializer(data=request.data, context={"tenant": request.tenant})
        serializer.is_valid(raise_exception=True)
        key = serializer.validated_data.get("idempotency_key")
        if key:
            existing = DriverAdvance.objects.filter(tenant=request.tenant, idempotency_key=key).select_related("driver").first()
            if existing:
                driver = serializer.validated_data["driver_id"]
                if existing.driver_id != driver.id or existing.amount != serializer.validated_data["amount"]:
                    return Response({"error": "This request key was already used for a different advance."}, status=409)
                return Response(driver_advance_data(existing), status=200)
        values = dict(serializer.validated_data)
        values["driver"] = values.pop("driver_id")
        try:
            with transaction.atomic():
                advance = DriverAdvance.objects.create(tenant=request.tenant, created_by=request.user, **values)
        except IntegrityError:
            return Response({"error": "This advance request was already recorded."}, status=409)
        audit(request, "FLEET_DRIVER_ADVANCE_RECORDED", advance, {"driver_id": str(advance.driver_id), "amount": str(advance.amount), "reference": advance.reference})
        return Response(driver_advance_data(advance), status=201)


class DriverAdvanceRecoveries(APIView):
    permission_classes = [HasTenantMembership]

    @transaction.atomic
    def post(self, request, advance_id):
        if request.membership.role not in EDIT_ROLES | REVIEW_ROLES:
            return Response({"error": "Advance recovery permission required."}, status=403)
        advance = get_object_or_404(DriverAdvance.objects.select_for_update().select_related("driver"), tenant=request.tenant, id=advance_id)
        serializer = DriverAdvanceRecoveryCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        key = serializer.validated_data.get("idempotency_key")
        if key:
            existing = DriverAdvanceRecovery.objects.filter(tenant=request.tenant, idempotency_key=key).first()
            if existing:
                if existing.advance_id != advance.id:
                    return Response({"error": "This request key was already used for another advance recovery."}, status=409)
                return Response(driver_advance_data(advance), status=200)
        salary = get_object_or_404(DriverSalaryRecord.objects.select_for_update().select_related("driver"), tenant=request.tenant, id=serializer.validated_data["salary_record_id"])
        if salary.driver_id != advance.driver_id:
            return Response({"error": "Choose an approved salary settlement for this same driver."}, status=400)
        if salary.status not in {DriverSalaryRecord.Status.APPROVED, DriverSalaryRecord.Status.PARTIALLY_PAID}:
            return Response({"error": "Advance recoveries can only be allocated to an approved, unpaid salary balance."}, status=409)
        amount = serializer.validated_data["amount"]
        advance_recovered = advance.recoveries.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        salary_recovered = salary.advance_recoveries.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        salary_paid = salary.payments.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        if amount > advance.amount - advance_recovered:
            return Response({"error": f"Recovery exceeds the advance balance of ₹{advance.amount - advance_recovered:.2f}."}, status=400)
        deductions = salary.adjustments.filter(kind=DriverSalaryAdjustment.Kind.DEDUCTION, status=DriverSalaryAdjustment.Status.APPROVED).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        if amount > salary.gross_earnings_amount - deductions - salary_recovered - salary_paid:
            return Response({"error": f"Recovery exceeds this salary settlement’s remaining balance of ₹{salary.gross_earnings_amount - deductions - salary_recovered - salary_paid:.2f}."}, status=400)
        try:
            with transaction.atomic():
                recovery = DriverAdvanceRecovery.objects.create(tenant=request.tenant, advance=advance, salary_record=salary, amount=amount, idempotency_key=key, created_by=request.user)
        except IntegrityError:
            return Response({"error": "This recovery request was already recorded."}, status=409)
        advance_recovered += recovery.amount
        advance.status = DriverAdvance.Status.RECOVERED if advance_recovered == advance.amount else DriverAdvance.Status.PARTIALLY_RECOVERED
        advance.save(update_fields=["status"])
        total_settled = salary_recovered + salary_paid + recovery.amount
        salary.status = DriverSalaryRecord.Status.SETTLED if total_settled == salary.gross_earnings_amount - deductions else DriverSalaryRecord.Status.PARTIALLY_PAID
        salary.save(update_fields=["status", "updated_at"])
        audit(request, "FLEET_DRIVER_ADVANCE_RECOVERED", recovery, {"advance_id": str(advance.id), "salary_record_id": str(salary.id), "amount": str(recovery.amount)})
        return Response({"advance": driver_advance_data(advance), "salary": DriverSalaryRecordSerializer(salary, context={"tenant": request.tenant}).data}, status=201)


class DriverPayPolicies(APIView):
    permission_classes = [HasTenantMembership]

    def get(self, request):
        if request.membership.role == Membership.Role.DRIVER:
            return Response({"error": "Driver pay policy access required."}, status=403)
        rows = DriverPayPolicy.objects.filter(tenant=request.tenant).select_related("driver").order_by("driver__name", "-effective_from")
        return Response(DriverPayPolicySerializer(rows, many=True, context={"tenant": request.tenant}).data)

    def post(self, request):
        if request.membership.role not in EDIT_ROLES | REVIEW_ROLES:
            return Response({"error": "Driver pay policy permission required."}, status=403)
        serializer = DriverPayPolicySerializer(data=request.data, context={"tenant": request.tenant})
        serializer.is_valid(raise_exception=True)
        try:
            policy = serializer.save(tenant=request.tenant, created_by=request.user)
        except IntegrityError:
            return Response({"error": "A policy already starts on that date. Review the driver’s effective-dated policies."}, status=409)
        audit(request, "FLEET_DRIVER_PAY_POLICY_CREATED", policy, {"driver_id": str(policy.driver_id), "basis": policy.basis, "rate": str(policy.rate), "effective_from": str(policy.effective_from), "effective_to": str(policy.effective_to or "")})
        return Response(DriverPayPolicySerializer(policy, context={"tenant": request.tenant}).data, status=201)


class DriverPayPolicyDetail(APIView):
    permission_classes = [HasTenantMembership]

    def patch(self, request, policy_id):
        if request.membership.role not in EDIT_ROLES | REVIEW_ROLES:
            return Response({"error": "Driver pay policy permission required."}, status=403)
        policy = get_object_or_404(DriverPayPolicy.objects.select_related("driver"), tenant=request.tenant, id=policy_id)
        if set(request.data.keys()) != {"effective_to"}:
            return Response({"error": "Only the policy end date can be changed after creation."}, status=400)
        try:
            end = date.fromisoformat(request.data["effective_to"]) if request.data["effective_to"] else None
        except (TypeError, ValueError):
            return Response({"error": "Use YYYY-MM-DD for the policy end date."}, status=400)
        if end and end < policy.effective_from:
            return Response({"error": "Policy end date cannot be before its start date."}, status=400)
        overlap = DriverPayPolicy.objects.filter(tenant=request.tenant, driver=policy.driver, effective_from__lte=end or date.max).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=policy.effective_from)).exclude(id=policy.id)
        if overlap.exists():
            return Response({"error": "The end date overlaps another pay policy for this driver."}, status=409)
        policy.effective_to = end
        policy.save(update_fields=["effective_to"])
        audit(request, "FLEET_DRIVER_PAY_POLICY_UPDATED", policy, {"effective_to": str(policy.effective_to or "")})
        return Response(DriverPayPolicySerializer(policy, context={"tenant": request.tenant}).data)


class DriverTripEarnings(APIView):
    permission_classes = [HasTenantMembership]

    def get(self, request):
        if request.membership.role == Membership.Role.DRIVER:
            return Response({"error": "Driver earnings access required."}, status=403)
        rows = DriverTripEarning.objects.filter(tenant=request.tenant).select_related("driver", "trip", "policy").order_by("-trip_date", "driver__name")
        result = []
        for earning in rows:
            salary = earning.salary_record
            result.append({"id": str(earning.id), "driver": {"id": str(earning.driver_id), "name": earning.driver.name}, "trip": {"id": str(earning.trip_id), "trip_number": earning.trip.trip_number}, "trip_date": earning.trip_date.isoformat(), "basis": earning.get_basis_display(), "units": f"{earning.units:.2f}", "rate": f"{earning.rate_snapshot:.2f}", "amount": f"{earning.amount:.2f}", "policy_id": str(earning.policy_id), "included_in_settlement": salary is not None, "settlement_status": salary.status if salary else "NOT_ALLOCATED"})
        return Response(result)
