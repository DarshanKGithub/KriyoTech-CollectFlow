"""Geofence geometry validation and GPS transition processing."""
import math
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction

from .models import FleetExceptionCase, FleetGeofence, FleetGeofenceDwellEpisode, FleetGeofenceEvent, FleetGeofenceTripState

EARTH_RADIUS_M = 6_371_008.8
MAX_ACCURACY_M = Decimal("100")
MIN_CONFIRMATIONS = 2
MIN_TRANSITION_SECONDS = 30
MAX_CANDIDATE_GAP = timedelta(minutes=5)


class GeofenceInputError(ValueError):
    pass


def _decimal(value, label, low, high):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise GeofenceInputError(f"{label} must be a number.")
    if not number.is_finite() or not low <= number <= high:
        raise GeofenceInputError(f"{label} is outside its allowed range.")
    return number


def validate_geometry(shape, geometry):
    if not isinstance(geometry, dict):
        raise GeofenceInputError("geometry must be an object.")
    if shape == FleetGeofence.Shape.CIRCLE:
        center = geometry.get("center")
        if not isinstance(center, (list, tuple)) or len(center) != 2:
            raise GeofenceInputError("Circle geometry needs center [longitude, latitude] and radius_m.")
        longitude = _decimal(center[0], "center longitude", Decimal("-180"), Decimal("180"))
        latitude = _decimal(center[1], "center latitude", Decimal("-90"), Decimal("90"))
        radius = _decimal(geometry.get("radius_m"), "radius_m", Decimal("25"), Decimal("100000"))
        if set(geometry) - {"center", "radius_m"}:
            raise GeofenceInputError("Circle geometry supports only center and radius_m.")
        return {"center": [float(longitude), float(latitude)], "radius_m": float(radius)}

    if shape != FleetGeofence.Shape.POLYGON:
        raise GeofenceInputError("shape must be CIRCLE or POLYGON.")
    coordinates = geometry.get("coordinates")
    if set(geometry) != {"type", "coordinates"} or geometry.get("type") != "Polygon":
        raise GeofenceInputError('Polygon geometry must be GeoJSON: {"type":"Polygon","coordinates":[ring]} (one outer ring, no holes).')
    if not isinstance(coordinates, list) or len(coordinates) != 1 or not isinstance(coordinates[0], list):
        raise GeofenceInputError("Only one polygon outer ring is supported.")
    ring = coordinates[0]
    if len(ring) > 501:
        raise GeofenceInputError("Polygon rings may contain at most 500 vertices.")
    points = []
    for point in ring:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise GeofenceInputError("Each polygon point must be [longitude, latitude].")
        longitude = _decimal(point[0], "polygon longitude", Decimal("-180"), Decimal("180"))
        latitude = _decimal(point[1], "polygon latitude", Decimal("-90"), Decimal("90"))
        points.append([float(longitude), float(latitude)])
    if len(points) > 1 and points[0] == points[-1]:
        points.pop()
    if len({(point[0], point[1]) for point in points}) < 3:
        raise GeofenceInputError("A polygon needs at least three distinct vertices.")
    points.append(points[0])
    return {"type": "Polygon", "coordinates": [points]}


def _distance_m(latitude_a, longitude_a, latitude_b, longitude_b):
    lat_a, lat_b = math.radians(latitude_a), math.radians(latitude_b)
    dlat = lat_b - lat_a
    dlon = math.radians(longitude_b - longitude_a)
    haversine = math.sin(dlat / 2) ** 2 + math.cos(lat_a) * math.cos(lat_b) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1, math.sqrt(haversine)))


def _inside_polygon(latitude, longitude, geometry):
    ring = geometry["coordinates"][0]
    inside = False
    for index in range(len(ring) - 1):
        x1, y1 = ring[index]
        x2, y2 = ring[index + 1]
        if (y1 > latitude) != (y2 > latitude):
            crossing_x = (x2 - x1) * (latitude - y1) / (y2 - y1) + x1
            if longitude < crossing_x:
                inside = not inside
    return inside


def contains_point(version, latitude, longitude, current_inside=False):
    """Return membership with a small GPS-accuracy boundary buffer."""
    geometry = version.geometry
    margin_m = 20
    if version.shape == FleetGeofence.Shape.CIRCLE:
        center_lon, center_lat = geometry["center"]
        distance = _distance_m(latitude, longitude, center_lat, center_lon)
        radius = geometry["radius_m"]
        boundary = distance - radius
        return boundary <= -margin_m if not current_inside else boundary < margin_m
    inside = _inside_polygon(latitude, longitude, geometry)
    ring = geometry["coordinates"][0]
    # Convert each edge into local metres around the GPS fix to estimate boundary clearance.
    scale_lon = 111_320 * max(0.01, math.cos(math.radians(latitude)))
    scale_lat = 110_574
    min_distance = float("inf")
    for index in range(len(ring) - 1):
        x1 = (ring[index][0] - longitude) * scale_lon
        y1 = (ring[index][1] - latitude) * scale_lat
        x2 = (ring[index + 1][0] - longitude) * scale_lon
        y2 = (ring[index + 1][1] - latitude) * scale_lat
        dx, dy = x2 - x1, y2 - y1
        length_squared = dx * dx + dy * dy
        fraction = max(0, min(1, -(x1 * dx + y1 * dy) / length_squared)) if length_squared else 0
        min_distance = min(min_distance, math.hypot(x1 + fraction * dx, y1 + fraction * dy))
    if inside:
        return min_distance >= margin_m if not current_inside else True
    return min_distance < margin_m if current_inside else False


def _sync_dwell_episode(sample, fence, version, inside, end_reason=""):
    episode = FleetGeofenceDwellEpisode.objects.select_for_update().filter(
        tenant_id=sample.tenant_id, trip_id=sample.trip_id, geofence=fence, ended_at__isnull=True,
    ).first()
    if not inside:
        if episode:
            episode.ended_at = sample.captured_at
            episode.last_sample_at = sample.captured_at
            episode.end_reason = end_reason or FleetGeofenceDwellEpisode.EndReason.DEPARTURE
            episode.last_latitude = sample.latitude
            episode.last_longitude = sample.longitude
            episode.save()
        return
    if episode and episode.version != version:
        episode.ended_at = sample.captured_at
        episode.last_sample_at = sample.captured_at
        episode.end_reason = FleetGeofenceDwellEpisode.EndReason.BOUNDARY_CHANGED
        episode.save()
        episode = None
    if not episode:
        episode = FleetGeofenceDwellEpisode.objects.create(tenant_id=sample.tenant_id, trip_id=sample.trip_id,
            geofence=fence, version=version, started_at=sample.captured_at, last_sample_at=sample.captured_at,
            sample_count=1, last_latitude=sample.latitude, last_longitude=sample.longitude)
    elif sample.captured_at > episode.last_sample_at:
        episode.last_sample_at = sample.captured_at
        episode.sample_count += 1
        episode.last_latitude = sample.latitude
        episode.last_longitude = sample.longitude
        episode.save()
    threshold = fence.dwell_alert_minutes
    if threshold and not episode.exception_case_id and (sample.captured_at - episode.started_at).total_seconds() >= threshold * 60:
        case, _ = FleetExceptionCase.objects.get_or_create(tenant_id=sample.tenant_id,
            source_key=f"geofence-dwell:{episode.id}", defaults={
                "category": "LONG_SITE_DWELL", "due_at": sample.captured_at + timedelta(minutes=30),
                "evidence": {"trip_id": str(sample.trip_id), "trip_number": sample.trip.trip_number,
                    "geofence_id": str(fence.id), "geofence_name": fence.name, "geofence_version": version,
                    "episode_id": str(episode.id), "observed_since": episode.started_at.isoformat(),
                    "observed_until": sample.captured_at.isoformat(), "sample_count": episode.sample_count,
                    "duration_seconds": int((sample.captured_at - episode.started_at).total_seconds()),
                    "latitude": str(sample.latitude), "longitude": str(sample.longitude),
                    "message": f"Trip {sample.trip.trip_number} has remained inside {fence.name} for at least {threshold} minutes. Confirm whether loading, queueing, or a delay explains the dwell."},
            })
        episode.exception_case = case
        episode.save(update_fields=["exception_case"])


@transaction.atomic
def record_geofence_sample(sample):
    """Emit stable arrival/departure transitions from accurate, ordered GPS fixes."""
    if sample.accuracy_m is None or sample.accuracy_m > MAX_ACCURACY_M:
        return 0
    fences = FleetGeofence.objects.filter(tenant_id=sample.tenant_id, active=True).prefetch_related("versions")
    emitted = 0
    for fence in fences:
        try:
            version = next(row for row in fence.versions.all() if row.version == fence.current_version)
        except StopIteration:
            continue
        state, _ = FleetGeofenceTripState.objects.get_or_create(
            tenant_id=sample.tenant_id, trip_id=sample.trip_id, geofence=fence,
            defaults={"version": version.version},
        )
        state = FleetGeofenceTripState.objects.select_for_update().get(pk=state.pk)
        if state.version != version.version:
            state.version = version.version
            state.inside = contains_point(version, float(sample.latitude), float(sample.longitude), False)
            state.candidate_inside = None
            state.candidate_count = 0
            state.candidate_since = None
            state.last_sample_at = sample.captured_at
            state.save()
            _sync_dwell_episode(sample, fence, version.version, False,
                FleetGeofenceDwellEpisode.EndReason.BOUNDARY_CHANGED)
            continue
        if state.last_sample_at and sample.captured_at <= state.last_sample_at:
            continue
        desired = contains_point(version, float(sample.latitude), float(sample.longitude), bool(state.inside))
        if state.inside is None and not desired:
            state.inside = False
            state.last_sample_at = sample.captured_at
            state.save()
            _sync_dwell_episode(sample, fence, version.version, False)
            continue
        if state.inside is None or desired != state.inside:
            if state.candidate_inside != desired or (state.candidate_since and sample.captured_at - state.candidate_since > MAX_CANDIDATE_GAP):
                state.candidate_inside = desired
                state.candidate_count = 1
                state.candidate_since = sample.captured_at
            else:
                state.candidate_count += 1
            if (state.candidate_count >= MIN_CONFIRMATIONS and state.candidate_since
                    and (sample.captured_at - state.candidate_since).total_seconds() >= MIN_TRANSITION_SECONDS):
                event_type = FleetGeofenceEvent.EventType.ARRIVAL if desired else FleetGeofenceEvent.EventType.DEPARTURE
                FleetGeofenceEvent.objects.create(tenant_id=sample.tenant_id, trip_id=sample.trip_id,
                    geofence=fence, version=version.version, source_sample=sample, event_type=event_type,
                    latitude=sample.latitude, longitude=sample.longitude, occurred_at=sample.captured_at)
                state.inside = desired
                state.candidate_inside = None
                state.candidate_count = 0
                state.candidate_since = None
                emitted += 1
        else:
            state.candidate_inside = None
            state.candidate_count = 0
            state.candidate_since = None
        state.last_sample_at = sample.captured_at
        state.save()
        _sync_dwell_episode(sample, fence, version.version, bool(state.inside))
    return emitted
