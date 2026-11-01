"""Tenant-scoped configuration and event APIs for fleet geofences."""
from collections.abc import Mapping
from uuid import UUID

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Membership
from accounts.permissions import HasTenantMembership
from audit.models import AuditLog
from .geofencing import GeofenceInputError, validate_geometry
from .models import FleetGeofence, FleetGeofenceEvent, FleetGeofenceVersion

READ_ROLES = {Membership.Role.OWNER, Membership.Role.FINANCE, Membership.Role.APPROVER, Membership.Role.FLEET}
EDIT_ROLES = {Membership.Role.OWNER, Membership.Role.FLEET}


def geofence_data(fence):
    version = next((row for row in fence.versions.all() if row.version == fence.current_version), None)
    return {"id": str(fence.id), "name": fence.name, "site_type": fence.site_type,
        "active": fence.active, "current_version": fence.current_version,
        "dwell_alert_minutes": fence.dwell_alert_minutes,
        "shape": version.shape if version else None, "geometry": version.geometry if version else None,
        "created_at": fence.created_at.isoformat(), "updated_at": fence.updated_at.isoformat()}


def has_roles(request, roles):
    return request.membership.role in roles


class FleetGeofences(APIView):
    permission_classes = [HasTenantMembership]

    def get(self, request):
        if not has_roles(request, READ_ROLES):
            return Response({"error": "Fleet tracking access required."}, status=403)
        fences = FleetGeofence.objects.filter(tenant=request.tenant).prefetch_related("versions").order_by("name", "id")
        if request.query_params.get("include_inactive") != "true":
            fences = fences.filter(active=True)
        rows = list(fences[:1001])
        has_more = len(rows) > 1000
        rows = rows[:1000]
        return Response({"geofences": [geofence_data(fence) for fence in rows], "has_more": has_more})

    def post(self, request):
        if not has_roles(request, EDIT_ROLES):
            return Response({"error": "Only workspace owners and fleet operators can manage geofences."}, status=403)
        if not isinstance(request.data, Mapping):
            return Response({"error": "A JSON object is required."}, status=400)
        data = request.data
        name = str(data.get("name", "")).strip()
        site_type = data.get("site_type", FleetGeofence.SiteType.OTHER)
        shape = data.get("shape")
        reason = str(data.get("reason", "")).strip()
        dwell_minutes = data.get("dwell_alert_minutes", 60)
        if not name or len(name) > 160:
            return Response({"error": "name is required and must be at most 160 characters."}, status=400)
        if site_type not in FleetGeofence.SiteType.values:
            return Response({"error": "site_type must be FACTORY, WAREHOUSE, CUSTOMER, or OTHER."}, status=400)
        if shape not in FleetGeofence.Shape.values:
            return Response({"error": "shape must be CIRCLE or POLYGON."}, status=400)
        if isinstance(dwell_minutes, bool) or not isinstance(dwell_minutes, int) or not 0 <= dwell_minutes <= 10080:
            return Response({"error": "dwell_alert_minutes must be an integer from 0 to 10080; zero disables dwell cases."}, status=400)
        if len(reason) < 8 or len(reason) > 300:
            return Response({"error": "Provide a reason between 8 and 300 characters."}, status=400)
        try:
            geometry = validate_geometry(shape, data.get("geometry"))
        except GeofenceInputError as exc:
            return Response({"error": str(exc)}, status=400)
        try:
            with transaction.atomic():
                fence = FleetGeofence.objects.create(tenant=request.tenant, name=name, site_type=site_type,
                    dwell_alert_minutes=dwell_minutes, created_by=request.user)
                FleetGeofenceVersion.objects.create(geofence=fence, version=1, shape=shape,
                    geometry=geometry, reason=reason, created_by=request.user)
                AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="FLEET_GEOFENCE_CREATED",
                    object_type="FleetGeofence", object_id=str(fence.id), metadata={"site_type": site_type, "shape": shape,
                        "version": 1, "dwell_alert_minutes": dwell_minutes, "reason": reason})
        except IntegrityError:
            return Response({"error": "A geofence with this name already exists in this workspace."}, status=409)
        return Response(geofence_data(fence), status=201)


class FleetGeofenceDetail(APIView):
    permission_classes = [HasTenantMembership]

    @transaction.atomic
    def patch(self, request, geofence_id):
        if not has_roles(request, EDIT_ROLES):
            return Response({"error": "Only workspace owners and fleet operators can manage geofences."}, status=403)
        if not isinstance(request.data, Mapping):
            return Response({"error": "A JSON object is required."}, status=400)
        fence = get_object_or_404(FleetGeofence.objects.select_for_update().prefetch_related("versions"), tenant=request.tenant, id=geofence_id)
        data = request.data
        try:
            expected_version = int(data.get("expected_version"))
        except (TypeError, ValueError):
            return Response({"error": "expected_version is required."}, status=400)
        if expected_version != fence.current_version:
            return Response({"error": "Geofence changed; reload the current version before editing.", "current_version": fence.current_version}, status=409)
        current = fence.versions.filter(version=fence.current_version).first()
        if not current:
            return Response({"error": "This geofence has no current geometry version."}, status=409)
        if "name" in data:
            name = str(data["name"]).strip()
            if not name or len(name) > 160:
                return Response({"error": "name must be between 1 and 160 characters."}, status=400)
            if FleetGeofence.objects.filter(tenant=request.tenant, name=name).exclude(id=fence.id).exists():
                return Response({"error": "A geofence with this name already exists in this workspace."}, status=409)
            fence.name = name
        if "site_type" in data:
            if data["site_type"] not in FleetGeofence.SiteType.values:
                return Response({"error": "site_type must be FACTORY, WAREHOUSE, CUSTOMER, or OTHER."}, status=400)
            fence.site_type = data["site_type"]
        if "active" in data:
            if not isinstance(data["active"], bool):
                return Response({"error": "active must be a boolean."}, status=400)
            fence.active = data["active"]
        if "dwell_alert_minutes" in data:
            dwell_minutes = data["dwell_alert_minutes"]
            if isinstance(dwell_minutes, bool) or not isinstance(dwell_minutes, int) or not 0 <= dwell_minutes <= 10080:
                return Response({"error": "dwell_alert_minutes must be an integer from 0 to 10080; zero disables dwell cases."}, status=400)
            fence.dwell_alert_minutes = dwell_minutes
        shape_changed = "shape" in data or "geometry" in data
        if shape_changed:
            shape = data.get("shape", current.shape)
            if shape not in FleetGeofence.Shape.values:
                return Response({"error": "shape must be CIRCLE or POLYGON."}, status=400)
            reason = str(data.get("reason", "")).strip()
            if len(reason) < 8 or len(reason) > 300:
                return Response({"error": "Geometry changes need a reason between 8 and 300 characters."}, status=400)
            try:
                geometry = validate_geometry(shape, data.get("geometry", current.geometry))
            except GeofenceInputError as exc:
                return Response({"error": str(exc)}, status=400)
            if shape != current.shape or geometry != current.geometry:
                version_number = fence.current_version + 1
                FleetGeofenceVersion.objects.create(geofence=fence, version=version_number, shape=shape,
                    geometry=geometry, reason=reason, created_by=request.user)
                fence.current_version = version_number
        fence.save()
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="FLEET_GEOFENCE_UPDATED",
            object_type="FleetGeofence", object_id=str(fence.id), metadata={"version": fence.current_version,
                "active": fence.active, "name": fence.name, "dwell_alert_minutes": fence.dwell_alert_minutes,
                "reason": str(data.get("reason", "")).strip()[:300]})
        return Response(geofence_data(fence))


class FleetGeofenceEvents(APIView):
    permission_classes = [HasTenantMembership]

    def get(self, request):
        if not has_roles(request, READ_ROLES):
            return Response({"error": "Fleet tracking access required."}, status=403)
        try:
            limit = int(request.query_params.get("limit", "100"))
            offset = int(request.query_params.get("offset", "0"))
            if not 1 <= limit <= 500 or not 0 <= offset <= 1000000:
                raise ValueError
        except (TypeError, ValueError):
            return Response({"error": "limit must be 1–500 and offset must be 0–1000000."}, status=400)
        filters = {"tenant": request.tenant}
        for parameter, field in (("trip_id", "trip_id"), ("geofence_id", "geofence_id")):
            value = request.query_params.get(parameter)
            if value:
                try:
                    filters[field] = UUID(value)
                except (TypeError, ValueError):
                    return Response({"error": f"{parameter} must be a UUID."}, status=400)
        for parameter, field in (("from", "occurred_at__gte"), ("to", "occurred_at__lte")):
            value = request.query_params.get(parameter)
            if value:
                parsed = parse_datetime(value)
                if not parsed or not timezone.is_aware(parsed):
                    return Response({"error": f"{parameter} must be an ISO timestamp with a timezone."}, status=400)
                filters[field] = parsed
        rows = list(FleetGeofenceEvent.objects.filter(**filters).select_related("geofence", "trip", "trip__vehicle", "trip__driver").order_by("-occurred_at", "-id")[offset:offset + limit + 1])
        has_more = len(rows) > limit
        rows = rows[:limit]
        events = [{"id": str(row.id), "event_type": row.event_type, "geofence_id": str(row.geofence_id),
            "geofence_name": row.geofence.name, "geofence_version": row.version, "trip_id": str(row.trip_id),
            "trip_number": row.trip.trip_number, "vehicle": row.trip.vehicle.registration_number,
            "driver": row.trip.driver.name, "latitude": str(row.latitude), "longitude": str(row.longitude),
            "occurred_at": row.occurred_at.isoformat()} for row in rows]
        return Response({"events": events, "count": len(events), "has_more": has_more,
            "next_offset": offset + limit if has_more else None})
