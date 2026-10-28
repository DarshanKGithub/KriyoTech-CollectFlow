"""Google Routes adapter. Provider credentials never leave the server."""
import math
import os
from datetime import timedelta
import json
from urllib.request import Request, urlopen
from urllib.error import URLError
from django.core.cache import caches
from django.utils import timezone
from django.db.models import Q
from rest_framework.response import Response
from rest_framework.views import APIView
from accounts.permissions import HasTenantMembership
from .models import FleetTrip, FleetTripLocation, FleetExceptionCase

cache=caches["fleet_tracking"]


def metres(a,b):
    lat1,lon1,lat2,lon2=map(math.radians,[a[0],a[1],b[0],b[1]])
    value=math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371000*2*math.asin(min(1,math.sqrt(value)))


def record_motion(trip,location):
    if location.accuracy_m is None or location.accuracy_m>100:return
    key=f"fleet:stop:{trip.tenant_id}:{trip.id}"
    try:previous=cache.get(key)
    except Exception:return
    point=[float(location.latitude),float(location.longitude)]
    now=location.captured_at
    if not previous or (now-previous["seen"]).total_seconds()>120 or metres(previous["point"],point)>200:
        previous={"point":point,"since":now,"seen":now}
    else:previous["seen"]=now
    try:cache.set(key,previous,1800)
    except Exception:return
    if (now-previous["since"]).total_seconds()>=900:
        FleetExceptionCase.objects.get_or_create(tenant_id=trip.tenant_id,source_key=f"stop:{trip.id}:{previous['since'].isoformat()}",
            defaults={"category":"PROLONGED_STOP","evidence":{"trip_id":str(trip.id),"trip_number":trip.trip_number,
                "message":"Phone GPS remained within approximately 200 metres for at least 15 minutes. Confirm the reason with the driver.",
                "observed_since":previous["since"].isoformat()},"due_at":timezone.now()+timedelta(minutes=30)})


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


def refresh_route(trip):
    from .access import fleet_enabled
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
    body={"origin":{"location":{"latLng":{"latitude":float(location.latitude),"longitude":float(location.longitude)}}},
        "destination":{"address":destination},"travelMode":"DRIVE","routingPreference":"TRAFFIC_AWARE","units":"METRIC"}
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
        geometry_key=f"fleet:route-geometry:{trip.tenant_id}:{trip.id}"
        try:path=cache.get(geometry_key)
        except Exception:path=None
        point=(float(location.latitude),float(location.longitude))
        if path and location.accuracy_m is not None and location.accuracy_m<=100 and distance_to_path(point,path)>2000:
            FleetExceptionCase.objects.get_or_create(tenant_id=trip.tenant_id,source_key=f"route-deviation:{trip.id}:{timezone.localdate()}",
                defaults={"category":"ROUTE_DEVIATION","evidence":{"trip_id":str(trip.id),"trip_number":trip.trip_number,
                    "message":"Fresh phone GPS is more than 2 km from the previously computed road route. Confirm diversion or planned stops."},"due_at":timezone.now()+timedelta(minutes=30)})
        if not path and route.get("polyline",{}).get("encodedPolyline"):
            try:cache.set(geometry_key,decode_polyline(route["polyline"]["encodedPolyline"]),1800)
            except Exception:pass
        return {"status":"UPDATED","eta":arrival.isoformat(),"distance_m":distance,"method":"GOOGLE_TRAFFIC"}
    except (URLError,OSError,ValueError,KeyError,IndexError,TypeError):
        FleetTrip.objects.filter(id=trip.id,tenant_id=trip.tenant_id).update(route_error="Google route request failed. Check provider access, quota, and destination.")
        FleetExceptionCase.objects.get_or_create(tenant_id=trip.tenant_id,source_key=f"route-provider:{trip.id}:{timezone.localdate()}",
            defaults={"category":"ROUTE_PROVIDER_RETRY","evidence":{"trip_id":str(trip.id),"message":"Google route lookup failed. Scheduled monitoring retries the request; check credentials, quota and destination."},"due_at":timezone.now()+timedelta(hours=1)})
        return {"error":"Google route request failed. Check provider access, quota, and destination.","status":"PROVIDER_ERROR"}


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
