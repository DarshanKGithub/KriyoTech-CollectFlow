"""Authenticated adapter for GPS hardware providers using the canonical fleet sample contract."""
import hashlib
import hmac
import json
import os
import re
from collections.abc import Mapping
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from uuid import NAMESPACE_URL, UUID, uuid5

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Membership
from accounts.permissions import HasTenantMembership
from audit.models import AuditLog
from .access import fleet_enabled
from .models import FleetGpsDevice, FleetTrip, FleetTripLocation, FleetTripLocationSample, FleetVehicle

DEVICE_NAME = re.compile(r"^[A-Z0-9_.-]{2,32}$")
MAX_BODY_BYTES = 16_384
SIGNATURE_WINDOW = timedelta(minutes=5)
PROVIDER_SAMPLE_RETENTION_WINDOW = timedelta(hours=24)


def _device_data(device):
    return {"id": str(device.id), "provider": device.provider, "device_id": device.device_id,
        "vehicle_id": str(device.vehicle_id), "vehicle": device.vehicle.registration_number,
        "active": device.active, "updated_at": device.updated_at.isoformat()}


class FleetGpsDevices(APIView):
    permission_classes = [HasTenantMembership]

    def get(self, request):
        if request.membership.role not in {Membership.Role.OWNER, Membership.Role.FLEET}:
            return Response({"error": "Only workspace owners and fleet operators can manage GPS devices."}, status=403)
        rows = FleetGpsDevice.objects.filter(tenant=request.tenant).select_related("vehicle").order_by("provider", "device_id")[:1000]
        return Response({"devices": [_device_data(row) for row in rows]})

    @transaction.atomic
    def post(self, request):
        if request.membership.role not in {Membership.Role.OWNER, Membership.Role.FLEET}:
            return Response({"error": "Only workspace owners and fleet operators can manage GPS devices."}, status=403)
        data = request.data
        if not isinstance(data, Mapping):
            return Response({"error": "A JSON object is required."}, status=400)
        raw_provider = data.get("provider")
        provider = str(data.get("provider", "")).strip().upper()
        device_id = str(data.get("device_id", "")).strip()
        reason = str(data.get("reason", "")).strip()
        if set(data) - {"provider", "device_id", "vehicle_id", "reason"}:
            return Response({"error": "Only provider, device_id, vehicle_id and reason are accepted."}, status=400)
        if not isinstance(raw_provider, str) or not DEVICE_NAME.fullmatch(provider) or not device_id or len(device_id) > 128:
            return Response({"error": "provider must be 2–32 letters, numbers, dots, underscores or hyphens; device_id is required and limited to 128 characters."}, status=400)
        if len(reason) < 8 or len(reason) > 300:
            return Response({"error": "Provide a reason between 8 and 300 characters."}, status=400)
        vehicle = FleetVehicle.objects.filter(tenant=request.tenant, id=data.get("vehicle_id")).first()
        if not vehicle:
            return Response({"error": "Vehicle not found in this workspace."}, status=404)
        try:
            with transaction.atomic():
                device = FleetGpsDevice.objects.create(tenant=request.tenant, provider=provider,
                    device_id=device_id, vehicle=vehicle, created_by=request.user)
        except IntegrityError:
            return Response({"error": "This provider device is already mapped in this workspace."}, status=409)
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="FLEET_GPS_DEVICE_CREATED",
            object_type="FleetGpsDevice", object_id=str(device.id), metadata={"provider": provider,
                "device_id": device_id, "vehicle_id": str(vehicle.id), "reason": reason})
        return Response(_device_data(device), status=201)


class FleetGpsDeviceDetail(APIView):
    permission_classes = [HasTenantMembership]

    @transaction.atomic
    def patch(self, request, device_id):
        if request.membership.role not in {Membership.Role.OWNER, Membership.Role.FLEET}:
            return Response({"error": "Only workspace owners and fleet operators can manage GPS devices."}, status=403)
        if not isinstance(request.data, Mapping):
            return Response({"error": "A JSON object is required."}, status=400)
        device = get_object_or_404(FleetGpsDevice.objects.select_for_update().select_related("vehicle"),
            tenant=request.tenant, id=device_id)
        data = request.data
        if set(data) - {"active", "vehicle_id", "reason", "expected_updated_at"}:
            return Response({"error": "Only active, vehicle_id, reason and expected_updated_at are accepted."}, status=400)
        expected = parse_datetime(str(data.get("expected_updated_at", "")))
        if not expected or not timezone.is_aware(expected):
            return Response({"error": "expected_updated_at with timezone is required."}, status=400)
        if expected != device.updated_at:
            return Response({"error": "GPS device mapping changed; reload before editing.", "updated_at": device.updated_at.isoformat()}, status=409)
        reason = str(data.get("reason", "")).strip()
        if len(reason) < 8 or len(reason) > 300:
            return Response({"error": "Provide a reason between 8 and 300 characters."}, status=400)
        if "active" in data:
            if not isinstance(data["active"], bool):
                return Response({"error": "active must be a boolean."}, status=400)
            device.active = data["active"]
        if "vehicle_id" in data:
            vehicle = FleetVehicle.objects.filter(tenant=request.tenant, id=data["vehicle_id"]).first()
            if not vehicle:
                return Response({"error": "Vehicle not found in this workspace."}, status=404)
            device.vehicle = vehicle
        device.save()
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="FLEET_GPS_DEVICE_UPDATED",
            object_type="FleetGpsDevice", object_id=str(device.id), metadata={"provider": device.provider,
                "device_id": device.device_id, "vehicle_id": str(device.vehicle_id), "active": device.active, "reason": reason})
        return Response(_device_data(device))


class FleetGpsProviderIntake(APIView):
    """POST a signed JSON event; signature is HMAC-SHA256(timestamp + '.' + exact request body)."""
    permission_classes = [AllowAny]
    authentication_classes = []

    @transaction.atomic
    def post(self, request):
        secret = os.environ.get("FLEET_GPS_WEBHOOK_SECRET", "").encode()
        if len(secret) < 32:
            return Response({"error": "GPS provider intake is not configured."}, status=503)
        body = request.body
        if len(body) > MAX_BODY_BYTES:
            return Response({"error": "GPS provider event exceeds the maximum payload size."}, status=413)
        timestamp_header = request.headers.get("X-Fleet-Timestamp", "")
        signature = request.headers.get("X-Fleet-Signature", "")
        if not timestamp_header.isdecimal():
            return Response({"error": "A Unix X-Fleet-Timestamp header is required."}, status=401)
        try:
            timestamp = int(timestamp_header)
        except (TypeError, ValueError):
            return Response({"error": "A Unix X-Fleet-Timestamp header is required."}, status=401)
        now = timezone.now()
        if abs(now.timestamp() - timestamp) > SIGNATURE_WINDOW.total_seconds():
            return Response({"error": "GPS provider signature timestamp is outside the five-minute replay window."}, status=401)
        expected_signature = hmac.new(secret, timestamp_header.encode() + b"." + body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected_signature, signature.lower()):
            return Response({"error": "GPS provider signature is invalid."}, status=401)
        try:
            data = json.loads(body)
            if not isinstance(data, dict):
                raise ValueError
            provider_value = data["provider"]
            device_value = data["device_id"]
            event_value = data["event_id"]
            if not isinstance(provider_value, str) or not isinstance(device_value, str) or not isinstance(event_value, (str, int)):
                raise ValueError
            provider = provider_value.strip().upper()
            device_id = device_value.strip()
            external_event_id = str(event_value).strip()
            captured_at = parse_datetime(str(data["captured_at"]))
            latitude = Decimal(str(data["latitude"]))
            longitude = Decimal(str(data["longitude"]))
            accuracy = Decimal(str(data["accuracy_m"])) if data.get("accuracy_m") not in (None, "") else None
            speed = Decimal(str(data["speed_kmh"])) if data.get("speed_kmh") not in (None, "") else None
            heading = Decimal(str(data["heading_degrees"])) if data.get("heading_degrees") not in (None, "") else None
        except (KeyError, ValueError, TypeError, InvalidOperation, ArithmeticError, json.JSONDecodeError):
            return Response({"error": "GPS provider event fields are invalid or incomplete."}, status=400)
        if (set(data) - {"provider", "device_id", "event_id", "captured_at", "latitude", "longitude", "accuracy_m", "speed_kmh", "heading_degrees"}
                or not DEVICE_NAME.fullmatch(provider) or not device_id or len(device_id) > 128
                or not external_event_id or len(external_event_id) > 160
                or not captured_at or not timezone.is_aware(captured_at)
                or not latitude.is_finite() or not -90 <= latitude <= 90
                or not longitude.is_finite() or not -180 <= longitude <= 180
                or (accuracy is not None and (not accuracy.is_finite() or not 0 <= accuracy <= 5000))
                or (speed is not None and (not speed.is_finite() or not 0 <= speed <= 432))
                or (heading is not None and (not heading.is_finite() or not 0 <= heading < 360))):
            return Response({"error": "GPS provider event values are outside their allowed ranges."}, status=400)
        if captured_at > now + timedelta(minutes=2) or captured_at < now - PROVIDER_SAMPLE_RETENTION_WINDOW:
            return Response({"error": "Provider GPS timestamps must be within the last 24 hours and no more than two minutes in the future."}, status=400)
        device = FleetGpsDevice.objects.select_related("vehicle", "tenant").filter(provider=provider,
            device_id=device_id, active=True).first()
        if not device or not fleet_enabled(device.tenant):
            return Response({"error": "GPS device is not actively mapped to an enabled workspace."}, status=404)
        from accounts.workspace_access import workspace_access_denial
        if workspace_access_denial(device.tenant, method="POST"):
            return Response({"error": "Workspace is not currently accepting GPS provider updates."}, status=403)
        trips = list(FleetTrip.objects.select_for_update().select_related("driver", "vehicle").filter(
            tenant_id=device.tenant_id, vehicle_id=device.vehicle_id, status=FleetTrip.Status.IN_PROGRESS)[:2])
        if len(trips) != 1:
            return Response({"error": "An active trip assignment for this vehicle is missing or ambiguous."}, status=409)
        trip = trips[0]
        canonical_event_id = uuid5(NAMESPACE_URL, f"fleet-gps:{device.tenant_id}:{provider}:{device_id}:{external_event_id}")
        if FleetTripLocationSample.objects.filter(tenant_id=device.tenant_id, client_event_id=canonical_event_id).exists():
            return Response({"accepted": True, "duplicate": True}, status=200)
        values = {"reported_by_id": trip.driver.user_id, "source_provider": provider, "latitude": latitude,
            "longitude": longitude, "accuracy_m": accuracy, "speed_kmh": speed, "heading_degrees": heading,
            "captured_at": captured_at, "client_event_id": canonical_event_id}
        try:
            with transaction.atomic():
                sample = FleetTripLocationSample.objects.create(tenant_id=device.tenant_id, trip=trip, **values)
        except IntegrityError:
            return Response({"accepted": True, "duplicate": True}, status=200)
        location = FleetTripLocation.objects.select_for_update().filter(tenant_id=device.tenant_id, trip=trip).first()
        if location and captured_at <= location.captured_at:
            return Response({"accepted": True, "historical_sample_recorded": True, "latest_unchanged": True}, status=200)
        if location:
            for field, value in values.items():
                setattr(location, field, value)
            location.save()
        else:
            location = FleetTripLocation.objects.create(tenant_id=device.tenant_id, trip=trip, **values)
        if captured_at >= now - timedelta(minutes=2):
            from .routing import record_motion, record_route_deviation
            from .geofencing import record_geofence_sample
            record_motion(trip, location)
            record_geofence_sample(sample)
            record_route_deviation(sample)
        return Response({"accepted": True, "duplicate": False, "trip_id": str(trip.id),
            "captured_at": captured_at.isoformat(), "source_provider": provider}, status=201)
