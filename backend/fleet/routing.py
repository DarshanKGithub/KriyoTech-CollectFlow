"""Google Routes adapter. Provider credentials never leave the server."""
import hashlib
import math
import os
import time
from datetime import timedelta
from decimal import Decimal
import json
from urllib.request import Request, urlopen
from urllib.error import URLError
from django.utils import timezone
from django.db import transaction
from django.db.models import F, Max, Q
from rest_framework.response import Response
from rest_framework.views import APIView
from accounts.permissions import HasTenantMembership
from .models import FleetExceptionCase, FleetGeofence, FleetGeofenceVersion, FleetGeofenceTripState, FleetRouteDeviationEpisode, FleetRouteProviderAttempt, FleetRouteSnapshot, FleetStopEpisode, FleetTrip, FleetTripLocation

STOP_RADIUS_M=200
STOP_MIN_DURATION=timedelta(minutes=15)
STOP_MAX_SAMPLE_GAP=timedelta(minutes=2)
STOP_MAX_SPEED_KMH=3
ROUTE_DEVIATION_THRESHOLD_M=2000
ROUTE_DEVIATION_CONFIRMATIONS=2
ROUTE_DEVIATION_CONFIRM_SECONDS=30
ROUTE_DEVIATION_MAX_GAP=timedelta(minutes=5)
ROUTE_DEVIATION_GPS_GAP=timedelta(minutes=2)
ROUTE_PROVIDER_CIRCUIT_WINDOW=timedelta(minutes=15)


@transaction.atomic
def _claim_route_provider_attempt(trip,now):
    """Apply a per-tenant rolling request budget and short failure circuit breaker."""
    type(trip.tenant).objects.select_for_update().get(pk=trip.tenant_id)
    recent=FleetRouteProviderAttempt.objects.filter(tenant_id=trip.tenant_id,requested_at__gte=now-timedelta(hours=24))
    try:
        daily_budget=max(0,int(os.environ.get("GOOGLE_ROUTES_DAILY_REQUEST_BUDGET","1000")))
    except (TypeError,ValueError):
        daily_budget=1000
    used=recent.count()
    if daily_budget==0 or used>=daily_budget:
        return None,{"status":"BUDGET_EXCEEDED","retry_after_seconds":max(1,int((recent.order_by("requested_at").first().requested_at+timedelta(hours=24)-now).total_seconds())) if used else 86400}
    recent_statuses=list(recent.order_by("-requested_at").values_list("status",flat=True)[:3])
    latest=recent.order_by("-requested_at").first()
    if len(recent_statuses)==3 and all(status==FleetRouteProviderAttempt.Status.FAILED for status in recent_statuses) and latest and now-latest.requested_at<ROUTE_PROVIDER_CIRCUIT_WINDOW:
        retry_after=max(1,int((latest.requested_at+ROUTE_PROVIDER_CIRCUIT_WINDOW-now).total_seconds()))
        return None,{"status":"CIRCUIT_OPEN","retry_after_seconds":retry_after}
    attempt=FleetRouteProviderAttempt.objects.create(tenant_id=trip.tenant_id,trip_id=trip.id)
    return attempt,None


def metres(a,b):
    lat1,lon1,lat2,lon2=map(math.radians,[a[0],a[1],b[0],b[1]])
    value=math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371000*2*math.asin(min(1,math.sqrt(value)))


@transaction.atomic
def record_motion(trip,location):
    """Persist stationary episodes; never infer engine idle without ignition data."""
    if location.accuracy_m is None or location.accuracy_m>100:
        return None
    now=location.captured_at
    episode=FleetStopEpisode.objects.select_for_update().filter(
        tenant_id=trip.tenant_id,trip_id=trip.id,ended_at__isnull=True).first()
    if episode and now<=episode.last_sample_at:
        return episode
    if episode and now-episode.last_sample_at>STOP_MAX_SAMPLE_GAP:
        episode.ended_at=episode.last_sample_at
        episode.status=FleetStopEpisode.Status.INTERRUPTED
        episode.save(update_fields=["ended_at","status"])
        episode=None
    speed=getattr(location,"speed_kmh",None)
    moving=speed is not None and speed>STOP_MAX_SPEED_KMH
    moved_far=bool(episode and metres(
        [float(episode.start_latitude),float(episode.start_longitude)],
        [float(location.latitude),float(location.longitude)])>STOP_RADIUS_M)
    if episode and (moving or moved_far):
        episode.ended_at=now
        episode.status=FleetStopEpisode.Status.CLOSED
        episode.last_sample_at=now
        episode.last_latitude=location.latitude
        episode.last_longitude=location.longitude
        episode.save()
        episode=None
    if moving:
        return None
    if not episode:
        episode=FleetStopEpisode.objects.create(tenant_id=trip.tenant_id,trip_id=trip.id,
            started_at=now,last_sample_at=now,start_latitude=location.latitude,start_longitude=location.longitude,
            last_latitude=location.latitude,last_longitude=location.longitude)
    else:
        episode.last_sample_at=now
        episode.last_latitude=location.latitude
        episode.last_longitude=location.longitude
        episode.sample_count+=1
        episode.save(update_fields=["last_sample_at","last_latitude","last_longitude","sample_count"])
    if (now-episode.started_at)<STOP_MIN_DURATION or episode.exception_case_id:
        return episode
    inside_site=FleetGeofenceTripState.objects.filter(tenant_id=trip.tenant_id,trip_id=trip.id,
        inside=True,geofence__active=True).select_related("geofence").first()
    episode.inside_geofence=inside_site.geofence if inside_site else None
    has_sites=FleetGeofence.objects.filter(tenant_id=trip.tenant_id,active=True).exists()
    category="LONG_SITE_STOP" if inside_site else ("STOP_OUTSIDE_SITE" if has_sites else "PROLONGED_STOP")
    message=(f"Trip {trip.trip_number} remained stationary inside {inside_site.geofence.name} for at least 15 minutes." if inside_site else
        (f"Trip {trip.trip_number} remained stationary outside configured sites for at least 15 minutes. Review whether the stop was authorized." if has_sites else
         f"Trip {trip.trip_number} remained within approximately 200 metres for at least 15 minutes. Confirm the reason with the driver."))
    if inside_site:
        episode.save(update_fields=["inside_geofence"])
        return episode
    case,_=FleetExceptionCase.objects.get_or_create(tenant_id=trip.tenant_id,source_key=f"stop-episode:{episode.id}",defaults={
        "category":category,"evidence":{"trip_id":str(trip.id),"trip_number":trip.trip_number,
            "episode_id":str(episode.id),"observed_since":episode.started_at.isoformat(),
            "observed_until":now.isoformat(),"sample_count":episode.sample_count,
            "duration_seconds":int((now-episode.started_at).total_seconds()),
            "latitude":str(location.latitude),"longitude":str(location.longitude),"message":message,
            "classification":"GPS stationary review signal; this does not establish an unauthorized stop or engine idle."},
        "due_at":now+timedelta(minutes=30)})
    episode.exception_case=case
    episode.save(update_fields=["inside_geofence","exception_case"])
    return episode


def decode_polyline(encoded):
    points=[];index=lat=lng=0
    while index<len(encoded):
        values=[]
        for _ in range(2):
            shift=result=0
            while True:
                value=ord(encoded[index])-63;index+=1;result|=(value&31)<<shift;shift+=5
                if value<32:break
            values.append(~(result>>1) if result&1 else result>>1)
        lat+=values[0];lng+=values[1];points.append((lat/1e5,lng/1e5))
    return points


def distance_to_path(point,path):
    # Local equirectangular projection, adequate for operational deviation signals.
    scale=math.cos(math.radians(point[0]));best=float("inf")
    for a,b in zip(path,path[1:]):
        ax=(a[1]-point[1])*scale*111195;ay=(a[0]-point[0])*111195
        bx=(b[1]-point[1])*scale*111195;by=(b[0]-point[0])*111195
        dx=bx-ax;dy=by-ay;length=dx*dx+dy*dy
        t=max(0,min(1,-(ax*dx+ay*dy)/length)) if length else 0
        best=min(best,math.hypot(ax+t*dx,ay+t*dy))
    return best


@transaction.atomic
def store_route_snapshot(*,trip,encoded_polyline,distance_m,duration_seconds,destination,generated_at=None):
    """Persist route geometry so later GPS checks do not depend on ephemeral cache state."""
    path=decode_polyline(encoded_polyline)
    if len(path)<2 or any(not math.isfinite(lat) or not math.isfinite(lon) or not -90<=lat<=90 or not -180<=lon<=180 for lat,lon in path):
        raise ValueError("The route provider returned invalid route geometry.")
    route_fingerprint=hashlib.sha256(f"{destination}\n{encoded_polyline}".encode()).hexdigest()
    locked_trip=FleetTrip.objects.select_for_update().get(tenant_id=trip.tenant_id,id=trip.id)
    existing=FleetRouteSnapshot.objects.filter(tenant_id=trip.tenant_id,trip=trip,route_fingerprint=route_fingerprint).first()
    if existing:
        return existing
    previous=FleetRouteSnapshot.objects.filter(tenant_id=trip.tenant_id,trip=trip).order_by("-version").first()
    version=(previous.version if previous else 0)+1
    snapshot=FleetRouteSnapshot.objects.create(tenant_id=trip.tenant_id,trip=trip,version=version,
        route_fingerprint=route_fingerprint,route_path=[[lat,lon] for lat,lon in path],
        distance_m=distance_m,duration_seconds=duration_seconds,destination=destination,
        generated_at=generated_at or timezone.now())
    FleetRouteDeviationEpisode.objects.filter(tenant_id=trip.tenant_id,trip=trip,
        status__in=[FleetRouteDeviationEpisode.Status.CANDIDATE,FleetRouteDeviationEpisode.Status.ACTIVE]).exclude(
        route_snapshot=snapshot).update(status=FleetRouteDeviationEpisode.Status.SUPERSEDED,
            end_reason=FleetRouteDeviationEpisode.EndReason.ROUTE_UPDATED,ended_at=generated_at or timezone.now())
    return snapshot


def _planned_site_at(tenant_id,latitude,longitude):
    from .geofencing import contains_point
    versions=FleetGeofenceVersion.objects.filter(geofence__tenant_id=tenant_id,geofence__active=True,
        version=F("geofence__current_version")).select_related("geofence")
    for version in versions:
        if contains_point(version,latitude,longitude,False):
            return version.geofence
    return None


def _finish_deviation(episode,*,status,end_reason,at):
    episode.status=status
    episode.end_reason=end_reason
    episode.ended_at=at
    episode.save(update_fields=["status","end_reason","ended_at"])


@transaction.atomic
def record_route_deviation(sample):
    """Confirm persistent route deviations from ordered, accurate phone GPS fixes."""
    if sample.accuracy_m is None or Decimal(str(sample.accuracy_m))>Decimal("100"):
        return None
    snapshot=FleetRouteSnapshot.objects.filter(tenant_id=sample.tenant_id,trip_id=sample.trip_id).order_by("-version").first()
    if not snapshot or len(snapshot.route_path)<2:
        return None
    episode=FleetRouteDeviationEpisode.objects.select_for_update().filter(tenant_id=sample.tenant_id,
        trip_id=sample.trip_id,status__in=[FleetRouteDeviationEpisode.Status.CANDIDATE,FleetRouteDeviationEpisode.Status.ACTIVE]).first()
    if episode and episode.route_snapshot_id!=snapshot.id:
        _finish_deviation(episode,status=FleetRouteDeviationEpisode.Status.SUPERSEDED,
            end_reason=FleetRouteDeviationEpisode.EndReason.ROUTE_UPDATED,at=sample.captured_at)
        episode=None
    if episode and sample.captured_at<=episode.last_sample_at:
        return episode
    if episode and sample.captured_at-episode.last_sample_at>ROUTE_DEVIATION_GPS_GAP:
        _finish_deviation(episode,status=FleetRouteDeviationEpisode.Status.INTERRUPTED,
            end_reason=FleetRouteDeviationEpisode.EndReason.GPS_GAP,at=episode.last_sample_at)
        episode=None
    latitude,longitude=float(sample.latitude),float(sample.longitude)
    planned_site=_planned_site_at(sample.tenant_id,latitude,longitude)
    distance=int(round(distance_to_path((latitude,longitude),snapshot.route_path)))
    if planned_site:
        if episode:
            _finish_deviation(episode,status=FleetRouteDeviationEpisode.Status.EXEMPTED,
                end_reason=FleetRouteDeviationEpisode.EndReason.PLANNED_SITE,at=sample.captured_at)
        return None
    if distance<=ROUTE_DEVIATION_THRESHOLD_M:
        if episode:
            _finish_deviation(episode,status=FleetRouteDeviationEpisode.Status.CLOSED,
                end_reason=FleetRouteDeviationEpisode.EndReason.REJOINED,at=sample.captured_at)
            return episode
        return None
    if not episode:
        episode=FleetRouteDeviationEpisode.objects.create(tenant_id=sample.tenant_id,trip_id=sample.trip_id,
            route_snapshot=snapshot,status=FleetRouteDeviationEpisode.Status.CANDIDATE,
            candidate_since=sample.captured_at,last_sample_at=sample.captured_at,
            candidate_count=1,sample_count=1,max_deviation_m=distance,last_deviation_m=distance,
            first_latitude=sample.latitude,first_longitude=sample.longitude,
            last_latitude=sample.latitude,last_longitude=sample.longitude)
    else:
        if sample.captured_at-episode.candidate_since>ROUTE_DEVIATION_MAX_GAP and episode.status==FleetRouteDeviationEpisode.Status.CANDIDATE:
            episode.candidate_since=sample.captured_at
            episode.candidate_count=1
            episode.first_latitude=sample.latitude
            episode.first_longitude=sample.longitude
        else:
            episode.candidate_count+=1
        episode.last_sample_at=sample.captured_at
        episode.last_deviation_m=distance
        episode.max_deviation_m=max(episode.max_deviation_m,distance)
        episode.last_latitude=sample.latitude
        episode.last_longitude=sample.longitude
        episode.sample_count+=1
        episode.save()
    if (episode.status==FleetRouteDeviationEpisode.Status.CANDIDATE
            and episode.candidate_count>=ROUTE_DEVIATION_CONFIRMATIONS
            and (sample.captured_at-episode.candidate_since).total_seconds()>=ROUTE_DEVIATION_CONFIRM_SECONDS):
        episode.status=FleetRouteDeviationEpisode.Status.ACTIVE
        episode.started_at=episode.candidate_since
        episode.save(update_fields=["status","started_at"])
        trip=FleetTrip.objects.select_related("vehicle","driver").get(tenant_id=sample.tenant_id,id=sample.trip_id)
        case,_=FleetExceptionCase.objects.get_or_create(tenant_id=sample.tenant_id,
            source_key=f"route-deviation-episode:{episode.id}",defaults={
                "category":"ROUTE_DEVIATION","due_at":sample.captured_at+timedelta(minutes=30),
                "evidence":{"trip_id":str(trip.id),"trip_number":trip.trip_number,
                    "vehicle":trip.vehicle.registration_number,"driver":trip.driver.name,
                    "episode_id":str(episode.id),"route_snapshot_id":str(snapshot.id),
                    "route_version":snapshot.version,"threshold_m":episode.threshold_m,
                    "observed_since":episode.started_at.isoformat(),"confirmed_at":sample.captured_at.isoformat(),
                    "sample_count":episode.sample_count,"deviation_m":episode.last_deviation_m,
                    "latitude":str(sample.latitude),"longitude":str(sample.longitude),
                    "message":f"Trip {trip.trip_number} remained more than {episode.threshold_m} metres from route version {snapshot.version} across multiple accurate GPS fixes. Review the diversion with the driver.",
                    "classification":"Route deviation review signal; a planned stop or provider route mismatch may explain it."}})
        episode.exception_case=case
        episode.save(update_fields=["exception_case"])
    return episode


def refresh_route(trip):
    from .access import fleet_enabled
    from accounts.workspace_access import workspace_access_denial
    if workspace_access_denial(trip.tenant, method="POST"):
        return {"error":"Workspace is not currently allowed to refresh routes.","status":"WORKSPACE_UNAVAILABLE"}
    if not fleet_enabled(trip.tenant):return {"error":"Fleet access is disabled for this workspace.","status":"DISABLED"}
    key=os.environ.get("GOOGLE_MAPS_ROUTES_API_KEY","")
    if not key:return {"error":"Google Maps Routes API key is not configured.","status":"NOT_CONFIGURED"}
    if not trip.tenant.settings.get("fleet_controls",{}).get("route_eta_enabled",False):
        return {"error":"Traffic ETA is disabled in this workspace's fleet settings.","status":"DISABLED"}
    location=FleetTripLocation.objects.filter(tenant_id=trip.tenant_id,trip=trip).first()
    if trip.status!="IN_PROGRESS" or not location or timezone.now()-location.captured_at>timedelta(minutes=2):
        return {"error":"An active trip with phone GPS from the last two minutes is required.","status":"GPS_REQUIRED"}
    destination=trip.destination or (trip.transport_order.destination if trip.transport_order_id else "")
    if not destination:return {"error":"Record the shipment delivery address first.","status":"DESTINATION_REQUIRED"}
    now=timezone.now()
    claimed=FleetTrip.objects.filter(tenant_id=trip.tenant_id,id=trip.id,status="IN_PROGRESS").filter(
        Q(route_attempted_at__isnull=True)|Q(route_attempted_at__lte=now-timedelta(minutes=1))).update(route_attempted_at=now)
    if not claimed:return {"error":"A road ETA request was recently attempted for this trip. Retry after one minute.","status":"THROTTLED"}
    attempt,blocked=_claim_route_provider_attempt(trip,now)
    if blocked:
        return {"error":"Routing provider request limit temporarily reached.",**blocked}
    body={"origin":{"location":{"latLng":{"latitude":float(location.latitude),"longitude":float(location.longitude)}}},
        "destination":{"address":destination},"travelMode":"DRIVE","routingPreference":"TRAFFIC_AWARE","units":"METRIC"}
    started=time.monotonic()
    try:
        request=Request("https://routes.googleapis.com/directions/v2:computeRoutes",data=json.dumps(body).encode(),method="POST",
            headers={"Content-Type":"application/json","X-Goog-Api-Key":key,"X-Goog-FieldMask":"routes.duration,routes.distanceMeters,routes.polyline.encodedPolyline"})
        with urlopen(request,timeout=12) as response:
            route=json.loads(response.read())["routes"][0]
        duration=float(route["duration"].rstrip("s"));distance=int(route["distanceMeters"])
        if not math.isfinite(duration) or not 0<=duration<=60*60*24*30 or not 0<=distance<=50000000:raise ValueError
        arrival=timezone.now()+timedelta(seconds=duration)
        FleetTrip.objects.filter(id=trip.id,tenant_id=trip.tenant_id,status="IN_PROGRESS").update(predicted_arrival_at=arrival,
            eta_source="GOOGLE_TRAFFIC",route_refreshed_at=timezone.now(),route_distance_m=distance,route_error="")
        attempt.status=FleetRouteProviderAttempt.Status.UPDATED
        attempt.completed_at=timezone.now()
        attempt.duration_ms=max(0,int((time.monotonic()-started)*1000))
        attempt.eta_at=arrival
        attempt.distance_m=distance
        attempt.save(update_fields=["status","completed_at","duration_ms","eta_at","distance_m"])
        encoded=route.get("polyline",{}).get("encodedPolyline")
        snapshot=store_route_snapshot(trip=trip,encoded_polyline=encoded,distance_m=distance,
            duration_seconds=int(duration),destination=destination) if encoded else None
        return {"status":"UPDATED","eta":arrival.isoformat(),"distance_m":distance,"method":"GOOGLE_TRAFFIC",
            "route_version":snapshot.version if snapshot else None,
            "deviation_monitoring":"ACTIVE" if snapshot else "ROUTE_GEOMETRY_UNAVAILABLE"}
    except (URLError,OSError,ValueError,KeyError,IndexError,TypeError) as exc:
        attempt.status=FleetRouteProviderAttempt.Status.FAILED
        attempt.completed_at=timezone.now()
        attempt.duration_ms=max(0,int((time.monotonic()-started)*1000))
        attempt.error_code="TIMEOUT" if isinstance(exc,TimeoutError) else ("HTTP_ERROR" if isinstance(exc,URLError) else "INVALID_RESPONSE")
        if isinstance(exc,URLError) and getattr(exc,"code",None):
            attempt.response_code=int(exc.code)
        attempt.save(update_fields=["status","completed_at","duration_ms","error_code","response_code"])
        FleetTrip.objects.filter(id=trip.id,tenant_id=trip.tenant_id).update(route_error="Google route request failed. Check provider access, quota, and destination.")
        FleetExceptionCase.objects.get_or_create(tenant_id=trip.tenant_id,source_key=f"route-provider:{trip.id}:{timezone.localdate()}",
            defaults={"category":"ROUTE_PROVIDER_RETRY","evidence":{"trip_id":str(trip.id),"message":"Google route lookup failed. Scheduled monitoring retries the request; check credentials, quota and destination."},"due_at":timezone.now()+timedelta(hours=1)})
        return {"error":"Google route request failed. Check provider access, quota, and destination.","status":"PROVIDER_ERROR",
            "retry_after_seconds":60}


class RouteEtaHistory(APIView):
    permission_classes=[HasTenantMembership]

    def get(self,request,trip_id):
        if request.membership.role not in {"OWNER","FINANCE","FLEET","APPROVER"}:
            return Response({"error":"Fleet access required."},status=403)
        trip=FleetTrip.objects.filter(tenant=request.tenant,id=trip_id).first()
        if not trip:
            return Response({"error":"Trip not found."},status=404)
        rows=FleetRouteProviderAttempt.objects.filter(tenant=request.tenant,trip=trip).order_by("-requested_at")[:100]
        now=timezone.now()
        return Response({"trip_id":str(trip.id),"eta":trip.predicted_arrival_at,
            "eta_source":trip.eta_source or None,"eta_updated_at":trip.route_refreshed_at,
            "eta_age_seconds":max(0,int((now-trip.route_refreshed_at).total_seconds())) if trip.route_refreshed_at else None,
            "history":[{"status":row.status,"requested_at":row.requested_at,"completed_at":row.completed_at,
                "eta_at":row.eta_at,"distance_m":row.distance_m,"duration_ms":row.duration_ms,
                "error_code":row.error_code,"response_code":row.response_code} for row in rows]})


class RouteIntegration(APIView):
    permission_classes=[HasTenantMembership]
    def get(self,request,trip_id=None):
        if request.membership.role not in {"OWNER","FINANCE","FLEET","APPROVER"}:return Response({"error":"Fleet access required."},status=403)
        return Response({"provider":"Google Maps Routes","configured":bool(os.environ.get("GOOGLE_MAPS_ROUTES_API_KEY")),
            "enabled":request.tenant.settings.get("fleet_controls",{}).get("route_eta_enabled",False),
            "limitations":"Drive routing does not certify truck height, weight, hazardous-goods restrictions, or driver working hours."})
    def post(self,request,trip_id=None):
        if request.membership.role not in {"OWNER","FINANCE","FLEET","APPROVER"}:return Response({"error":"Fleet access required."},status=403)
        if not trip_id:return Response({"error":"Choose a trip to refresh its road ETA."},status=400)
        trip=FleetTrip.objects.filter(tenant=request.tenant,id=trip_id).select_related("tenant","transport_order").first()
        if not trip:return Response({"error":"Trip not found."},status=404)
        result=refresh_route(trip)
        return Response(result,status=200 if result["status"]=="UPDATED" else 503)
