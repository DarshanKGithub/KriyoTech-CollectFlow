import json
import os
import re
import hashlib
import hmac
from datetime import timedelta
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
from django.conf import settings
from django.core.mail import send_mail,get_connection
from django.db import transaction
from django.utils import timezone
from django.http import HttpResponse
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from accounts.permissions import HasTenantMembership
from .models import ShipmentAccessLink,ShipmentNotice,FleetExceptionCase


def provider_status():
    whatsapp_keys=["WHATSAPP_ACCESS_TOKEN","WHATSAPP_PHONE_NUMBER_ID","WHATSAPP_GRAPH_VERSION","WHATSAPP_SHIPMENT_TEMPLATE"]
    return {"email_configured":bool(getattr(settings,"EMAIL_HOST","") and "smtp" in settings.EMAIL_BACKEND),
        "whatsapp_configured":all(os.environ.get(key) for key in whatsapp_keys),
        "google_routes_configured":bool(os.environ.get("GOOGLE_MAPS_ROUTES_API_KEY")),
        "whatsapp_template_parameters":["order number","shipment status","estimated arrival"],
        "notice":"Accepted means submitted to the provider; it does not confirm delivery to the recipient."}


def queue_customer_notices():
    from .access import fleet_enabled
    count=0;now=timezone.now()
    links=ShipmentAccessLink.objects.filter(revoked_at__isnull=True,expires_at__gt=now,tenant__is_deleted=False).select_related("tenant","trip__transport_order")
    for link in links:
        if not fleet_enabled(link.tenant):continue
        trip=link.trip;order=trip.transport_order
        if not order or not link.consent_note:continue
        events=[(f"status:{order.status}",order.status)]
        if order.delivery_due_at and trip.predicted_arrival_at and trip.predicted_arrival_at>order.delivery_due_at and not trip.delivery_at:
            events.append((f"delay:{now.date()}","DELIVERY_DELAY_RISK"))
        for key,status in events:
            for channel,recipient in (("EMAIL",link.notify_email),("WHATSAPP",link.notify_phone)):
                if recipient:
                    delivery_key=hashlib.sha256(f"{link.tenant_id}:{trip.id}:{recipient.casefold()}:{key}:{channel}".encode()).hexdigest()
                    _,created=ShipmentNotice.objects.get_or_create(delivery_key=delivery_key,
                        defaults={"link":link,"event_key":key,"channel":channel,"payload":{"recipient":recipient,"order_number":order.order_number,"status":status,
                            "eta":trip.predicted_arrival_at.isoformat() if trip.predicted_arrival_at else "Not yet available"}})
                    count+=int(created)
    return count


def send_notice(notice):
    p=notice.payload
    if notice.channel=="EMAIL":
        if not provider_status()["email_configured"]:return "FAILED","SMTP email is not configured.",""
        try:
            sent=send_mail(f"Shipment {p['order_number']} update",f"Status: {p['status']}\nEstimated arrival: {p['eta']}\nContact your transporter for shipment queries.",settings.DEFAULT_FROM_EMAIL,[p["recipient"]],fail_silently=False,connection=get_connection(timeout=15))
            return ("ACCEPTED","","") if sent else ("FAILED","Email backend did not accept the message.","")
        except Exception:
            return "UNKNOWN","Email send result is uncertain; check your mail provider before retrying.",""
    if not provider_status()["whatsapp_configured"]:return "FAILED","WhatsApp Business credentials and approved template are not configured.",""
    version=os.environ["WHATSAPP_GRAPH_VERSION"];phone_id=os.environ["WHATSAPP_PHONE_NUMBER_ID"]
    if not re.fullmatch(r"v\d+\.\d+",version) or not phone_id.isdigit():return "FAILED","WhatsApp API version or sender ID is invalid.",""
    payload={"messaging_product":"whatsapp","to":p["recipient"].lstrip("+"),"type":"template","template":{
        "name":os.environ["WHATSAPP_SHIPMENT_TEMPLATE"],"language":{"code":os.environ.get("WHATSAPP_TEMPLATE_LANGUAGE","en_US")},
        "components":[{"type":"body","parameters":[{"type":"text","text":str(p[key])} for key in ["order_number","status","eta"]]}]}}
    request=Request(f"https://graph.facebook.com/{version}/{phone_id}/messages",data=json.dumps(payload).encode(),method="POST",
        headers={"Content-Type":"application/json","Authorization":f"Bearer {os.environ['WHATSAPP_ACCESS_TOKEN']}"})
    try:
        with urlopen(request,timeout=15) as response:result=json.loads(response.read())
        reference=str(result.get("messages",[{}])[0].get("id",""))
        return ("ACCEPTED","",reference) if reference else ("UNKNOWN","WhatsApp response had no message reference.","")
    except HTTPError as error:
        if error.code==429:return "PENDING","Provider rate limit; retry scheduled.",""
        return ("FAILED",f"WhatsApp rejected the request (HTTP {error.code}). Check template and account configuration.","") if error.code<500 else ("UNKNOWN","WhatsApp send result is uncertain; check provider logs.","")
    except (URLError,OSError,ValueError,KeyError,IndexError):
        return "UNKNOWN","WhatsApp send result is uncertain; check provider logs before retrying.",""


def recover_stale_notices():
    cutoff=timezone.now()-timedelta(minutes=5)
    ids=list(ShipmentNotice.objects.filter(status="PROCESSING",updated_at__lt=cutoff).values_list("id",flat=True)[:100])
    recovered=0
    from audit.models import AuditLog
    for notice_id in ids:
        with transaction.atomic():
            row=ShipmentNotice.objects.select_for_update(of=("self",)).select_related("link").get(id=notice_id)
            if row.status!="PROCESSING" or row.updated_at>=cutoff:continue
            row.status="UNKNOWN";row.last_error="Worker interrupted; check provider logs before retrying.";row.save(update_fields=["status","last_error","updated_at"])
            AuditLog.objects.create(tenant_id=row.link.tenant_id,action="CUSTOMER_NOTICE_WORKER_INTERRUPTED",object_type="ShipmentNotice",object_id=str(row.id),metadata={"status":"UNKNOWN"})
            FleetExceptionCase.objects.get_or_create(tenant_id=row.link.tenant_id,source_key=f"customer-notice:{row.id}",defaults={"category":"CUSTOMER_NOTIFICATION_FAILURE","evidence":{"notice_id":str(row.id),"message":row.last_error},"due_at":timezone.now()+timedelta(hours=1)})
            recovered+=1
    return recovered


def process_notices(notice_id=None):
    from .access import fleet_enabled
    now=timezone.now()
    # A worker interrupted after sending must never blindly resend the same message.
    recover_stale_notices()
    pending=ShipmentNotice.objects.filter(status="PENDING",next_attempt_at__lte=now)
    if notice_id is not None:pending=pending.filter(id=notice_id)
    ids=list(pending.values_list("id",flat=True)[:100])
    processed=0
    for notice_id in ids:
        with transaction.atomic():
            notice=ShipmentNotice.objects.select_for_update(of=("self",)).select_related("link__tenant").get(id=notice_id)
            if notice.status!="PENDING":continue
            recipient=notice.link.notify_email if notice.channel=="EMAIL" else notice.link.notify_phone
            if not fleet_enabled(notice.link.tenant) or notice.link.revoked_at or notice.link.expires_at<=now or not recipient or recipient!=notice.payload["recipient"]:
                notice.status="CANCELLED";notice.save(update_fields=["status","updated_at"]);continue
            notice.status="PROCESSING";notice.attempts+=1;notice.save(update_fields=["status","attempts","updated_at"])
        status,error,reference=send_notice(notice)
        if status=="PENDING" and notice.attempts>=5:status="FAILED";error="Provider rate limit persisted after five attempts. Review before retrying."
        notice.status=status;notice.last_error=error;notice.provider_reference=reference[:200];notice.next_attempt_at=timezone.now()+timedelta(minutes=min(60,2**notice.attempts));notice.save()
        from audit.models import AuditLog
        AuditLog.objects.create(tenant_id=notice.link.tenant_id,action="CUSTOMER_NOTICE_ATTEMPT",object_type="ShipmentNotice",object_id=str(notice.id),
            metadata={"channel":notice.channel,"attempt":notice.attempts,"status":status,"error":error,"provider_reference":reference[:200]})
        if status in {"FAILED","UNKNOWN"}:
            FleetExceptionCase.objects.get_or_create(tenant_id=notice.link.tenant_id,source_key=f"customer-notice:{notice.id}",defaults={"category":"CUSTOMER_NOTIFICATION_FAILURE",
                "evidence":{"message":error,"notice_id":str(notice.id),"channel":notice.channel},"due_at":timezone.now()+timedelta(hours=1)})
        processed+=1
    return processed


class CustomerNotificationStatus(APIView):
    permission_classes=[HasTenantMembership]
    def get(self,request):
        if request.membership.role not in {"OWNER","FINANCE","FLEET","APPROVER"}:return Response({"error":"Fleet review access required."},status=403)
        rows=ShipmentNotice.objects.filter(link__tenant=request.tenant).order_by("-created_at")[:200]
        return Response({**provider_status(),"notices":[{"id":str(r.id),"channel":r.channel,"status":r.status,"event":r.event_key,"attempts":r.attempts,"last_error":r.last_error,"provider_reference":r.provider_reference} for r in rows]})
    def post(self,request):
        from uuid import UUID
        from .views import audit
        if request.membership.role not in {"OWNER","FINANCE","FLEET"}:return Response({"error":"Fleet edit access required."},status=403)
        try:notice_id=UUID(str(request.data.get("notice_id")))
        except (ValueError,TypeError):return Response({"error":"Choose a valid failed notice."},status=400)
        reason=str(request.data.get("reason","")).strip()[:500]
        with transaction.atomic():
            row=ShipmentNotice.objects.select_for_update().filter(id=notice_id,link__tenant=request.tenant).first()
            if not row:return Response({"error":"Notice not found."},status=404)
            if row.status not in {"FAILED","UNKNOWN"} or not reason or request.data.get("provider_checked") is not True:
                return Response({"error":"Check provider logs, confirm it was not sent, and provide a retry reason."},status=409)
            row.status="PENDING";row.next_attempt_at=timezone.now();row.save(update_fields=["status","next_attempt_at","updated_at"])
            audit(request,"CUSTOMER_NOTICE_RETRY_AUTHORIZED",row,{"reason":reason})
        return Response({"status":"PENDING"})


class WhatsAppDeliveryWebhook(APIView):
    authentication_classes=[]
    permission_classes=[AllowAny]
    def get(self,request):
        configured=os.environ.get("WHATSAPP_WEBHOOK_VERIFY_TOKEN","")
        supplied=request.query_params.get("hub.verify_token","")
        if configured and request.query_params.get("hub.mode")=="subscribe" and hmac.compare_digest(configured,supplied):
            return HttpResponse(request.query_params.get("hub.challenge",""),content_type="text/plain")
        return Response({"error":"Verification failed."},status=403)
    def post(self,request):
        secret=os.environ.get("WHATSAPP_APP_SECRET","")
        body=request.body
        if len(body)>1024*1024:return Response({"error":"Payload too large."},status=413)
        signature=request.headers.get("X-Hub-Signature-256","")
        expected="sha256="+hmac.new(secret.encode(),body,hashlib.sha256).hexdigest()
        if not secret or not hmac.compare_digest(signature,expected):return Response({"error":"Invalid signature."},status=403)
        try:data=json.loads(body)
        except (ValueError,UnicodeDecodeError):return Response({"error":"Invalid JSON."},status=400)
        if not isinstance(data,dict):return Response({"error":"Invalid webhook envelope."},status=400)
        from audit.models import AuditLog
        ranks={"ACCEPTED":0,"SENT":1,"DELIVERED":2,"READ":3}
        for entry in data.get("entry",[]) or []:
            if not isinstance(entry,dict):continue
            for change in entry.get("changes",[]) or []:
                if not isinstance(change,dict) or not isinstance(change.get("value"),dict):continue
                for event in change.get("value",{}).get("statuses",[]) or []:
                    if not isinstance(event,dict):continue
                    reference=str(event.get("id",""))
                    state=str(event.get("status","")).upper()
                    if not reference or state not in {"SENT","DELIVERED","READ","FAILED"}:continue
                    with transaction.atomic():
                        row=ShipmentNotice.objects.select_for_update(of=("self",)).select_related("link").filter(channel="WHATSAPP",provider_reference=reference).first()
                        if not row or row.status==state:continue
                        if row.status in {"DELIVERED","READ"} and (state=="FAILED" or ranks.get(state,0)<ranks[row.status]):continue
                        if state!="FAILED" and ranks.get(state,0)<ranks.get(row.status,0):continue
                        before=row.status;row.status=state
                        if state=="FAILED":row.last_error="WhatsApp reported delivery failure. Check the message reference with the provider."
                        elif state in {"DELIVERED","READ"}:row.last_error=""
                        row.save(update_fields=["status","last_error","updated_at"])
                        AuditLog.objects.create(tenant_id=row.link.tenant_id,action="WHATSAPP_DELIVERY_UPDATED",object_type="ShipmentNotice",object_id=str(row.id),metadata={"previous_status":before,"status":state,"provider_reference":reference})
                        if state=="FAILED":
                            FleetExceptionCase.objects.get_or_create(tenant_id=row.link.tenant_id,source_key=f"customer-delivery:{row.id}",defaults={"category":"CUSTOMER_NOTIFICATION_FAILURE","evidence":{"notice_id":str(row.id),"message":row.last_error},"due_at":timezone.now()+timedelta(hours=1)})
        return Response({"received":True})
