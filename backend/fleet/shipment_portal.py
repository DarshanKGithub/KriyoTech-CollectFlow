from partners.services import frontend_link
import hashlib
import secrets
import re
from uuid import UUID
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from datetime import timedelta
from django.conf import settings
from django.http import FileResponse, HttpResponse
from django.utils import timezone
from django.utils.html import escape
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView
from accounts.permissions import HasTenantMembership
from .models import ShipmentAccessLink, FleetTrip, FleetExceptionCase, TransportInvoice
from .views import EDIT_ROLES, REVIEW_ROLES, audit


class ShipmentLinks(APIView):
    permission_classes = [HasTenantMembership]
    def get(self, request):
        if request.membership.role not in EDIT_ROLES | REVIEW_ROLES:
            return Response({"error":"Shipment sharing access required."},status=403)
        rows=ShipmentAccessLink.objects.filter(tenant=request.tenant).select_related("trip").order_by("-created_at")[:500]
        trips=FleetTrip.objects.filter(tenant=request.tenant,transport_order__isnull=False).order_by("-created_at")[:500]
        return Response({"links":[{"id":str(r.id),"trip":r.trip.trip_number,"expires_at":r.expires_at.isoformat(),"revoked":bool(r.revoked_at)} for r in rows],
            "trips":[{"id":str(t.id),"trip_number":t.trip_number} for t in trips]})
    def post(self, request):
        if request.membership.role not in EDIT_ROLES:
            return Response({"error":"Fleet edit access required."},status=403)
        try: trip_id=UUID(str(request.data.get("trip_id")))
        except (ValueError,TypeError):return Response({"error":"Choose a valid shipment."},status=400)
        email=str(request.data.get("notify_email","")).strip()
        phone=str(request.data.get("notify_phone","")).strip()
        consent=str(request.data.get("consent_note","")).strip()[:500]
        if len(email)>254:return Response({"error":"Notification email is too long."},status=400)
        try:
            if email:validate_email(email)
        except ValidationError:return Response({"error":"Enter a valid notification email."},status=400)
        if phone and not re.fullmatch(r"\+[1-9]\d{7,14}",phone):return Response({"error":"Use an international phone number starting with +."},status=400)
        if (email or phone) and (request.data.get("customer_consented") is not True or not consent):return Response({"error":"Record customer consent and its source before enabling notifications."},status=400)
        trip=FleetTrip.objects.filter(tenant=request.tenant,id=trip_id,transport_order__isnull=False).first()
        if not trip:return Response({"error":"Choose a customer shipment in this workspace."},status=404)
        raw=secrets.token_urlsafe(32)
        link=ShipmentAccessLink.objects.create(tenant=request.tenant,trip=trip,token_hash=hashlib.sha256(raw.encode()).hexdigest(),expires_at=timezone.now()+timedelta(days=7),created_by=request.user,notify_email=email,notify_phone=phone,consent_note=consent)
        audit(request,"SHIPMENT_LINK_CREATED",link,{"trip_id":str(trip.id),"expires_at":link.expires_at.isoformat()})
        response=Response({"id":str(link.id),"url":frontend_link(f"/portal/shipment/{raw}"),"expires_at":link.expires_at.isoformat()},status=201)
        response["Cache-Control"]="no-store"
        return response
    def delete(self,request):
        if request.membership.role not in EDIT_ROLES:return Response({"error":"Fleet edit access required."},status=403)
        try: link_id=UUID(str(request.data.get("id")))
        except (ValueError,TypeError):return Response({"error":"Choose a valid link."},status=400)
        link=ShipmentAccessLink.objects.filter(tenant=request.tenant,id=link_id).first()
        if not link:return Response({"error":"Link not found."},status=404)
        link.revoked_at=timezone.now();link.save(update_fields=["revoked_at"])
        audit(request,"SHIPMENT_LINK_REVOKED",link)
        return Response({"revoked":True})


class ShipmentThrottle(SimpleRateThrottle):
    scope="shipment_portal"
    rate="30/hour"
    def get_cache_key(self,request,view):
        return self.cache_format % {"scope":self.scope,"ident":self.get_ident(request)+hashlib.sha256(str(view.kwargs.get("token","")).encode()).hexdigest()}


class PublicShipment(APIView):
    authentication_classes=[]
    permission_classes=[AllowAny]
    throttle_classes=[ShipmentThrottle]
    def link(self,token,method="GET"):
        from .access import fleet_enabled
        from accounts.workspace_access import workspace_access_denial
        link=ShipmentAccessLink.objects.filter(token_hash=hashlib.sha256(token.encode()).hexdigest(),expires_at__gt=timezone.now(),revoked_at__isnull=True,tenant__is_deleted=False).select_related("tenant","trip__transport_order__customer","trip__delivery_proof").first()
        return link if link and not workspace_access_denial(link.tenant,method=method) and fleet_enabled(link.tenant, "fleet_portal") else None
    def finalize_response(self,request,response,*args,**kwargs):
        response=super().finalize_response(request,response,*args,**kwargs)
        response["Cache-Control"]="no-store";response["Referrer-Policy"]="no-referrer";response["X-Robots-Tag"]="noindex, nofollow"
        return response
    def get(self,request,token,download=None):
        link=self.link(token,request.method)
        if not link:return Response({"error":"This shipment link has expired or was revoked."},status=404)
        trip=link.trip;order=trip.transport_order
        if not order:return Response({"error":"Shipment unavailable."},status=404)
        invoice=TransportInvoice.objects.filter(tenant=link.tenant,trip=trip).exclude(status__in=["DRAFT","CANCELLED"]).first()
        if download=="pod":
            proof=trip.delivery_proof
            if not proof or proof.tenant_id!=link.tenant_id:return Response({"error":"Delivery proof is not available."},status=404)
            try:return FileResponse(proof.file.open("rb"),as_attachment=True,filename=proof.filename,content_type="application/octet-stream")
            except OSError:return Response({"error":"Delivery proof file is currently unavailable."},status=404)
        if download=="invoice":
            if not invoice:return Response({"error":"Issued invoice is not available."},status=404)
            html=f'<!doctype html><html><head><meta charset="utf-8"><title>Shipment invoice</title></head><body><h1>Invoice {escape(invoice.invoice_number)}</h1><p>Customer: {escape(order.customer.name)}</p><p>Order: {escape(order.order_number)}</p><p>Date: {invoice.invoice_date}</p><p>Amount: INR {invoice.amount}</p><p>Status: {escape(invoice.status)}</p></body></html>'
            response=HttpResponse(html,content_type="text/html");response["Content-Disposition"]='attachment; filename="shipment-invoice.html"';return response
        if download:return Response({"error":"Unknown shipment download."},status=404)
        issues=FleetExceptionCase.objects.filter(tenant=link.tenant,evidence__portal_id=str(link.id)).order_by("-created_at")[:50]
        return Response({"order_number":order.order_number,"customer":order.customer.name,"origin":order.origin,"destination":order.destination,
            "status":order.status,"pickup_at":trip.pickup_at,"loaded_at":trip.loaded_at,"delivery_at":trip.delivery_at,
            "eta":trip.predicted_arrival_at,"eta_source":trip.eta_source,"eta_updated_at":trip.route_refreshed_at,
            "delivery_proof_available":bool(trip.delivery_proof_id),"invoice_available":bool(invoice),
            "issues":[{"reference":str(i.id),"status":i.status,"description":i.evidence.get("message"),"resolution":i.public_resolution,"created_at":i.created_at.isoformat()} for i in issues]})
    def post(self,request,token,download=None):
        if download:return Response({"error":"Downloads do not accept issue submissions."},status=405)
        link=self.link(token,request.method)
        if not link:return Response({"error":"This shipment link has expired or was revoked."},status=404)
        if request.data.get("action")=="unsubscribe":
            same_shipment=ShipmentAccessLink.objects.filter(tenant=link.tenant,trip=link.trip)
            if link.notify_email:same_shipment.filter(notify_email__iexact=link.notify_email).update(notify_email="")
            if link.notify_phone:same_shipment.filter(notify_phone=link.notify_phone).update(notify_phone="")
            link.notify_email="";link.notify_phone="";link.save(update_fields=["notify_email","notify_phone"])
            return Response({"unsubscribed":True})
        description=str(request.data.get("description","")).strip()
        if not 5<=len(description)<=1000:return Response({"error":"Describe the delivery issue or dispute in 5–1000 characters."},status=400)
        case=FleetExceptionCase.objects.create(tenant=link.tenant,source_key=f"customer:{secrets.token_hex(16)}",category="CUSTOMER_DELIVERY_DISPUTE",
            evidence={"portal_id":str(link.id),"trip_id":str(link.trip_id),"message":description},due_at=timezone.now()+timedelta(hours=24))
        return Response({"reference":str(case.id),"status":case.status},status=201)
