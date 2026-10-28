import hashlib
import hmac
import json
import mimetypes
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone as dt_timezone

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import HasTenantMembership
from audit.models import AuditLog
from documents.models import Document
from invoices.models import Invoice
from vendors.models import Vendor

from .models import WhatsAppEndpoint, WhatsAppMessage, WhatsAppMessageDraft, WhatsAppConsent


MAX_INBOUND_BYTES = 12 * 1024 * 1024
ALLOWED_INVOICE_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/heic"}
FINANCE_ROLES = {"OWNER", "FINANCE", "FINANCE_MANAGER", "ADMIN"}
OPT_OUT_KEYWORDS = {"stop", "stopall", "unsubscribe", "cancel", "end", "quit"}
WHATSAPP_RECONCILIATION_DELAY = timedelta(minutes=5)
WHATSAPP_DELIVERY_PREDECESSORS = {
    "SENT": {"QUEUED", "SENT"},
    "DELIVERED": {"QUEUED", "SENT", "DELIVERED"},
    "READ": {"QUEUED", "SENT", "DELIVERED", "READ"},
    "FAILED": {"QUEUED", "SENT", "FAILED"},
}


def _phone(value):
    digits = re.sub(r"\D", "", str(value or ""))
    return f"+{digits}" if digits else ""


def _meta_request(url, *, method="GET", payload=None):
    token = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
    if not token:
        raise RuntimeError("WhatsApp Business is not connected. Add WHATSAPP_ACCESS_TOKEN to the backend environment.")
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as response:
        raw = response.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise RuntimeError("WhatsApp returned an unexpectedly large response.")
    return json.loads(raw.decode("utf-8")) if raw else {}


def _download_meta_media(media_id):
    version = os.getenv("WHATSAPP_GRAPH_API_VERSION", "")
    if not version or not re.fullmatch(r"v\d+\.\d+", version):
        raise RuntimeError("Set WHATSAPP_GRAPH_API_VERSION to the Graph API version enabled for your Meta app.")
    info = _meta_request(f"https://graph.facebook.com/{version}/{urllib.parse.quote(media_id, safe='')}")
    url = info.get("url", "")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"lookaside.fbsbx.com", "graph.facebook.com"}:
        raise RuntimeError("WhatsApp returned an invalid media location.")
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {os.getenv('WHATSAPP_ACCESS_TOKEN', '')}"})
    with urllib.request.urlopen(req, timeout=20) as response:
        content = response.read(MAX_INBOUND_BYTES + 1)
        content_type = response.headers.get_content_type()
    if len(content) > MAX_INBOUND_BYTES:
        raise RuntimeError("Invoice attachment is larger than the 12 MB WhatsApp intake limit.")
    content_type = info.get("mime_type") or content_type
    if content_type not in ALLOWED_INVOICE_TYPES:
        raise RuntimeError("This attachment type is not supported. Send a PDF, JPEG, PNG, or HEIC invoice.")
    return content, content_type, info.get("filename") or f"whatsapp-{media_id}{mimetypes.guess_extension(content_type) or '.bin'}"


class WhatsAppWebhook(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        expected = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
        supplied = request.query_params.get("hub.verify_token", "")
        challenge = request.query_params.get("hub.challenge", "")
        if expected and hmac.compare_digest(expected, supplied) and request.query_params.get("hub.mode") == "subscribe":
            return HttpResponse(challenge, content_type="text/plain")
        return HttpResponse(status=403)

    def post(self, request):
        secret = os.getenv("WHATSAPP_APP_SECRET", "")
        signature = request.headers.get("X-Hub-Signature-256", "")
        expected = "sha256=" + hmac.new(secret.encode(), request.body, hashlib.sha256).hexdigest() if secret else ""
        if not secret or not hmac.compare_digest(expected, signature):
            return Response({"error": "Invalid WhatsApp webhook signature"}, status=403)
        try:
            payload = json.loads(request.body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return Response({"error": "Invalid webhook payload"}, status=400)
        processed = 0
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                phone_id = value.get("metadata", {}).get("phone_number_id")
                endpoint = WhatsAppEndpoint.objects.filter(phone_number_id=phone_id, active=True).select_related("tenant").first()
                if not endpoint:
                    continue
                for item in value.get("messages", []):
                    self._receive(endpoint, item)
                    processed += 1
                for status in value.get("statuses", []):
                    message = WhatsAppMessage.objects.filter(tenant=endpoint.tenant, external_id=status.get("id", ""), direction="OUTBOUND").first()
                    if message:
                        mapped = {"sent": "SENT", "delivered": "DELIVERED", "read": "READ", "failed": "FAILED"}.get(status.get("status"))
                        if mapped and message.status in WHATSAPP_DELIVERY_PREDECESSORS[mapped]:
                            previous_status = message.status
                            message.status = mapped
                            message.error = json.dumps(status.get("errors", []))[:2000] if mapped == "FAILED" else ""
                            message.save(update_fields=["status", "error"])
                            if previous_status != mapped:
                                AuditLog.objects.create(tenant=endpoint.tenant, actor=None, action="WHATSAPP_DELIVERY_STATUS_UPDATED",
                                    object_type="WhatsAppMessage", object_id=str(message.id), metadata={"status": mapped})
        return Response({"received": processed})

    @transaction.atomic
    def _receive(self, endpoint, item):
        external_id = item.get("id")
        sender = _phone(item.get("from"))
        if not external_id or not sender:
            return
        if WhatsAppMessage.objects.filter(tenant=endpoint.tenant, external_id=external_id).exists():
            return
        message_type = item.get("type", "text")
        body = item.get("text", {}).get("body", "") if message_type == "text" else ""
        media_item = item.get(message_type, {}) if message_type in {"document", "image"} else {}
        vendor = next((row for row in Vendor.objects.filter(tenant=endpoint.tenant).only("id", "name", "contact_phone") if _phone(row.contact_phone) == sender), None)
        invoice = None
        document = None
        error = ""
        if media_item.get("id"):
            try:
                content, media_type, filename = _download_meta_media(media_item["id"])
                document = Document(tenant=endpoint.tenant, filename=filename, media_type=media_type,
                    checksum_sha256=hashlib.sha256(content).hexdigest(), size_bytes=len(content))
                document.file.save(filename, ContentFile(content), save=True)
                invoice = Invoice.objects.create(tenant=endpoint.tenant, vendor=vendor, document=document,
                    supplier_name=vendor.name if vendor else "", source_channel="WHATSAPP", status=Invoice.Status.UPLOADED)
                from invoices.extraction import queue_invoice_extraction
                queue_invoice_extraction(invoice)
            except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError, ValueError) as exc:
                error = str(exc)[:1000]
        elif message_type not in {"text", "interactive", "button", "reaction"}:
            error = f"Unsupported WhatsApp message type: {message_type}"
        if not invoice and vendor and body:
            text = body.casefold()
            invoice = next((row for row in Invoice.objects.filter(tenant=endpoint.tenant, vendor=vendor).exclude(status__in=["EXPORTED", "REJECTED"]).only("id", "invoice_number") if row.invoice_number and row.invoice_number.casefold() in text), None)
        timestamp = item.get("timestamp")
        received_at = datetime.fromtimestamp(int(timestamp), tz=dt_timezone.utc) if str(timestamp or "").isdigit() else timezone.now()
        message = WhatsAppMessage.objects.create(tenant=endpoint.tenant, endpoint=endpoint, external_id=external_id,
            contact_phone=sender, direction="INBOUND", message_type=message_type, body=body,
            status="RECEIVED" if not error else "FAILED", invoice=invoice, document=document,
            metadata={"media_id": media_item.get("id", "")}, error=error, received_at=received_at)
        command_match = re.match(r"^\s*([a-z]+)", body.casefold())
        normalized_command = command_match.group(1) if command_match else ""
        if message_type == "text" and normalized_command in OPT_OUT_KEYWORDS:
            WhatsAppConsent.objects.update_or_create(
                tenant=endpoint.tenant, phone=sender,
                defaults={"vendor": vendor, "status": WhatsAppConsent.Status.OPTED_OUT,
                    "source": WhatsAppConsent.Source.INBOUND_KEYWORD,
                    "evidence_note": f"Inbound opt-out keyword: {normalized_command.upper()}", "updated_by": None},
            )
            AuditLog.objects.create(tenant=endpoint.tenant, actor=None, action="WHATSAPP_CONSENT_OPTED_OUT",
                object_type="WhatsAppConsent", object_id=sender,
                metadata={"source": "INBOUND_KEYWORD", "keyword": normalized_command.upper()})
        AuditLog.objects.create(tenant=endpoint.tenant, actor=None, action="WHATSAPP_MESSAGE_RECEIVED",
            object_type="WhatsAppMessage", object_id=str(message.id), metadata={"message_type": message_type, "invoice_id": str(invoice.id) if invoice else None})
        if invoice and document:
            AuditLog.objects.create(tenant=endpoint.tenant, actor=None, action="WHATSAPP_INVOICE_DRAFT_CREATED",
                object_type="Invoice", object_id=str(invoice.id), metadata={"document_id": str(document.id), "vendor_matched": bool(vendor)})


class WhatsAppMessages(APIView):
    permission_classes = [HasTenantMembership]

    def get(self, request):
        rows = WhatsAppMessage.objects.filter(tenant=request.tenant).select_related("invoice", "document").order_by("-created_at")[:200]
        return Response([{"id": str(x.id), "external_id": x.external_id, "contact_phone": x.contact_phone,
            "direction": x.direction, "message_type": x.message_type, "body": x.body, "status": x.status,
            "invoice_id": str(x.invoice_id) if x.invoice_id else None,
            "invoice_number": x.invoice.invoice_number if x.invoice_id else None,
            "document_id": str(x.document_id) if x.document_id else None, "error": x.error,
            "created_at": x.created_at} for x in rows])

    def post(self, request):
        if request.membership.role not in FINANCE_ROLES:
            return Response({"error": "Finance role required"}, status=403)
        invoice_id = request.data.get("invoice_id")
        endpoint_id = request.data.get("endpoint_id")
        try:
            invoice = Invoice.objects.select_related("vendor").get(id=invoice_id, tenant=request.tenant)
            endpoint = WhatsAppEndpoint.objects.get(id=endpoint_id, tenant=request.tenant, active=True)
        except (Invoice.DoesNotExist, WhatsAppEndpoint.DoesNotExist, ValueError, TypeError):
            return Response({"error": "Choose an invoice and an active WhatsApp number in this workspace."}, status=404)
        purpose = request.data.get("purpose", "OTHER")
        if purpose not in WhatsAppMessageDraft.Purpose.values:
            return Response({"error": "Choose a supported message purpose."}, status=400)
        recipient = _phone(request.data.get("recipient_phone") or getattr(invoice.vendor, "contact_phone", ""))
        body = str(request.data.get("body", "")).strip()
        if not recipient or len(body) < 4 or len(body) > 1024:
            return Response({"error": "A valid vendor phone and a message between 4 and 1024 characters are required."}, status=400)
        if not WhatsAppConsent.objects.filter(tenant=request.tenant, phone=recipient, status=WhatsAppConsent.Status.OPTED_IN).exists():
            return Response({"error": "No recorded WhatsApp opt-in exists for this number. Record verified consent before drafting."}, status=409)
        draft = WhatsAppMessageDraft.objects.create(tenant=request.tenant, invoice=invoice, endpoint=endpoint,
            recipient_phone=recipient, recipient_consent_confirmed=True, purpose=purpose, body=body, created_by=request.user)
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="WHATSAPP_MESSAGE_DRAFTED",
            object_type="WhatsAppMessageDraft", object_id=str(draft.id), metadata={"invoice_id": str(invoice.id), "purpose": purpose, "recipient_consent_confirmed": True})
        return Response(self._payload(draft), status=201)

    @staticmethod
    def _payload(draft):
        return {"id": str(draft.id), "invoice_id": str(draft.invoice_id), "invoice_number": draft.invoice.invoice_number,
            "recipient_phone": draft.recipient_phone, "purpose": draft.purpose, "body": draft.body,
            "status": draft.status, "recipient_consent_confirmed": draft.recipient_consent_confirmed,
            "error": draft.error, "created_at": draft.created_at, "send_started_at": draft.send_started_at,
            "reconciliation_available": bool(draft.status == WhatsAppMessageDraft.Status.SENDING and draft.send_started_at and timezone.now() - draft.send_started_at >= WHATSAPP_RECONCILIATION_DELAY)}


class WhatsAppEndpoints(APIView):
    permission_classes = [HasTenantMembership]

    def get(self, request):
        endpoints = WhatsAppEndpoint.objects.filter(tenant=request.tenant).order_by("-created_at")
        return Response([{"id": str(x.id), "phone_number_id": x.phone_number_id,
            "display_phone_number": x.display_phone_number, "active": x.active} for x in endpoints])

    def post(self, request):
        if request.membership.role not in {"OWNER", "ADMIN"}:
            return Response({"error": "Workspace owner or admin role required to connect a WhatsApp number."}, status=403)
        phone_id = str(request.data.get("phone_number_id", "")).strip()
        if not phone_id.isdigit():
            return Response({"error": "Enter the numeric phone number ID from Meta WhatsApp Manager."}, status=400)
        endpoint, created = WhatsAppEndpoint.objects.get_or_create(phone_number_id=phone_id,
            defaults={"tenant": request.tenant, "display_phone_number": str(request.data.get("display_phone_number", "")).strip()})
        if endpoint.tenant_id != request.tenant.id:
            return Response({"error": "That Meta phone number is already connected to another workspace."}, status=409)
        if not created:
            endpoint.display_phone_number = str(request.data.get("display_phone_number", endpoint.display_phone_number)).strip()
            endpoint.active = True
            endpoint.save(update_fields=["display_phone_number", "active"])
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="WHATSAPP_NUMBER_CONNECTED",
            object_type="WhatsAppEndpoint", object_id=str(endpoint.id), metadata={"phone_number_id": phone_id})
        return Response({"id": str(endpoint.id), "phone_number_id": endpoint.phone_number_id,
            "display_phone_number": endpoint.display_phone_number, "active": endpoint.active}, status=201 if created else 200)


class WhatsAppDrafts(WhatsAppMessages):
    def get(self, request):
        drafts = WhatsAppMessageDraft.objects.filter(tenant=request.tenant).select_related("invoice").order_by("-created_at")[:200]
        return Response([self._payload(row) for row in drafts])


class WhatsAppConsents(APIView):
    permission_classes = [HasTenantMembership]

    def get(self, request):
        rows = WhatsAppConsent.objects.filter(tenant=request.tenant).select_related("vendor", "updated_by").order_by("-updated_at")[:500]
        return Response([{"id": str(row.id), "phone": row.phone, "status": row.status, "source": row.source,
            "evidence_note": row.evidence_note, "vendor_id": str(row.vendor_id) if row.vendor_id else None,
            "vendor_name": row.vendor.name if row.vendor_id else None,
            "updated_by": row.updated_by.get_full_name() if row.updated_by else None, "updated_at": row.updated_at}
            for row in rows])

    @transaction.atomic
    def post(self, request):
        if request.membership.role not in FINANCE_ROLES:
            return Response({"error": "Finance role required to record WhatsApp consent."}, status=403)
        action = request.data.get("action")
        if action not in {"opt_in", "opt_out"}:
            return Response({"error": "Choose opt_in or opt_out."}, status=400)
        evidence = str(request.data.get("evidence_note", "")).strip()
        if len(evidence) < 8:
            return Response({"error": "Add a short note describing the consent or opt-out evidence."}, status=400)
        vendor = None
        vendor_id = request.data.get("vendor_id")
        if vendor_id:
            vendor = Vendor.objects.filter(tenant=request.tenant, id=vendor_id).first()
            if not vendor:
                return Response({"error": "Vendor not found in this workspace."}, status=404)
        phone = _phone(request.data.get("phone") or (vendor.contact_phone if vendor else ""))
        digits = phone[1:] if phone.startswith("+") else ""
        if not 8 <= len(digits) <= 15:
            return Response({"error": "Enter a valid international phone number with country code."}, status=400)
        if vendor and vendor.contact_phone and _phone(vendor.contact_phone) != phone:
            return Response({"error": "The phone must match the selected vendor record."}, status=400)
        status_value = WhatsAppConsent.Status.OPTED_IN if action == "opt_in" else WhatsAppConsent.Status.OPTED_OUT
        consent, created = WhatsAppConsent.objects.update_or_create(
            tenant=request.tenant, phone=phone,
            defaults={"vendor": vendor, "status": status_value, "source": WhatsAppConsent.Source.MANUAL,
                "evidence_note": evidence[:2000], "updated_by": request.user},
        )
        AuditLog.objects.create(tenant=request.tenant, actor=request.user,
            action="WHATSAPP_CONSENT_OPTED_IN" if action == "opt_in" else "WHATSAPP_CONSENT_OPTED_OUT",
            object_type="WhatsAppConsent", object_id=str(consent.id),
            metadata={"phone": phone, "source": "MANUAL", "vendor_id": str(vendor.id) if vendor else None,
                "created": created, "evidence_note": evidence[:500]})
        return Response({"id": str(consent.id), "phone": consent.phone, "status": consent.status,
            "source": consent.source, "updated_at": consent.updated_at}, status=201 if created else 200)


class WhatsAppMessageInvoiceLink(APIView):
    permission_classes = [HasTenantMembership]

    def patch(self, request, message_id):
        if request.membership.role not in FINANCE_ROLES:
            return Response({"error": "Finance role required"}, status=403)
        message = WhatsAppMessage.objects.filter(tenant=request.tenant, id=message_id).first()
        invoice = Invoice.objects.filter(tenant=request.tenant, id=request.data.get("invoice_id")).first()
        if not message or not invoice:
            return Response({"error": "Choose a message and invoice from this workspace."}, status=404)
        message.invoice = invoice
        message.save(update_fields=["invoice"])
        AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="WHATSAPP_MESSAGE_LINKED_TO_INVOICE",
            object_type="WhatsAppMessage", object_id=str(message.id), metadata={"invoice_id": str(invoice.id)})
        return Response({"id": str(message.id), "invoice_id": str(invoice.id), "invoice_number": invoice.invoice_number})


class WhatsAppDraftSend(APIView):
    permission_classes = [HasTenantMembership]

    def post(self, request, draft_id):
        if request.membership.role not in FINANCE_ROLES:
            return Response({"error": "Finance role required"}, status=403)
        with transaction.atomic():
            draft = WhatsAppMessageDraft.objects.select_for_update(of=("self",)).select_related("endpoint", "invoice").filter(
                id=draft_id, tenant=request.tenant).first()
            if not draft:
                return Response({"error": "Message draft not found."}, status=404)
            if draft.status != WhatsAppMessageDraft.Status.DRAFT:
                return Response({"error": "This draft is already being sent, sent, or failed. Create a new draft to try again."}, status=409)
            consent = WhatsAppConsent.objects.select_for_update().filter(
                tenant=request.tenant, phone=draft.recipient_phone, status=WhatsAppConsent.Status.OPTED_IN).first()
            if not consent:
                return Response({"error": "This number has opted out or has no current WhatsApp opt-in. The draft was not sent."}, status=409)
        version = os.getenv("WHATSAPP_GRAPH_API_VERSION", "")
        template = os.getenv("WHATSAPP_APPROVED_TEMPLATE", "")
        language = os.getenv("WHATSAPP_TEMPLATE_LANGUAGE", "en")
        if not version or not re.fullmatch(r"v\d+\.\d+", version) or not template:
            return Response({"error": "WhatsApp sending is not configured. Set the Graph API version and an approved one-placeholder utility template."}, status=503)
        if not os.getenv("WHATSAPP_ACCESS_TOKEN"):
            return Response({"error": "WhatsApp Business is not connected. Add the Meta system user token on the backend."}, status=503)
        # Claim before the network call so concurrent clicks cannot send twice. If the
        # process stops during delivery, keep the record visible as SENDING for review.
        with transaction.atomic():
            consent = WhatsAppConsent.objects.select_for_update().filter(
                tenant=request.tenant, phone=draft.recipient_phone, status=WhatsAppConsent.Status.OPTED_IN).first()
            if not consent:
                return Response({"error": "This number has opted out or has no current WhatsApp opt-in. The draft was not sent."}, status=409)
            claimed = WhatsAppMessageDraft.objects.filter(id=draft.id, status=WhatsAppMessageDraft.Status.DRAFT).update(
                status=WhatsAppMessageDraft.Status.SENDING, sent_by=request.user, send_started_at=timezone.now(), error="")
        if not claimed:
            return Response({"error": "This message is already being sent."}, status=409)
        payload = {"messaging_product": "whatsapp", "to": draft.recipient_phone.lstrip("+"), "type": "template",
            "template": {"name": template, "language": {"code": language}, "components": [{"type": "body", "parameters": [{"type": "text", "text": draft.body}]}]}}
        try:
            result = _meta_request(f"https://graph.facebook.com/{version}/{draft.endpoint.phone_number_id}/messages", method="POST", payload=payload)
            external_id = result["messages"][0]["id"]
        except urllib.error.HTTPError as exc:
            if exc.code >= 500:
                draft.error = f"Meta returned HTTP {exc.code}; the message outcome is unknown. Check Meta WhatsApp Manager before reconciling."
                draft.save(update_fields=["error"])
                AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="WHATSAPP_MESSAGE_OUTCOME_UNKNOWN",
                    object_type="WhatsAppMessageDraft", object_id=str(draft.id), metadata={"invoice_id": str(draft.invoice_id), "purpose": draft.purpose, "provider_status": exc.code})
                return Response({"error": "Meta returned a server error, so the send outcome is unknown. Check Meta WhatsApp Manager; do not send again until you reconcile the outcome."}, status=502)
            draft.status = WhatsAppMessageDraft.Status.FAILED
            draft.error = str(exc)[:1000]
            draft.save(update_fields=["status", "error"])
            AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="WHATSAPP_MESSAGE_SEND_FAILED",
                object_type="WhatsAppMessageDraft", object_id=str(draft.id), metadata={"invoice_id": str(draft.invoice_id), "purpose": draft.purpose})
            return Response({"error": "WhatsApp did not accept the message. Review the integration and create a new draft after fixing it."}, status=502)
        except (urllib.error.URLError, TimeoutError, RuntimeError, KeyError, IndexError, ValueError) as exc:
            draft.error = f"Provider outcome is unknown. Check Meta WhatsApp Manager before reconciling. {str(exc)[:800]}"[:1000]
            draft.save(update_fields=["error"])
            AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="WHATSAPP_MESSAGE_OUTCOME_UNKNOWN",
                object_type="WhatsAppMessageDraft", object_id=str(draft.id), metadata={"invoice_id": str(draft.invoice_id), "purpose": draft.purpose})
            return Response({"error": "The request timed out or returned an unreadable response. Check Meta WhatsApp Manager; do not send again until you reconcile the outcome."}, status=502)
        with transaction.atomic():
            message = WhatsAppMessage.objects.create(tenant=request.tenant, endpoint=draft.endpoint, external_id=external_id,
                contact_phone=draft.recipient_phone, direction="OUTBOUND", message_type="template", body=draft.body,
                status=WhatsAppMessage.Status.SENT, invoice=draft.invoice, sent_by=request.user,
                metadata={"purpose": draft.purpose, "template": template})
            draft.status = WhatsAppMessageDraft.Status.SENT
            draft.sent_by = request.user
            draft.sent_at = timezone.now()
            draft.message = message
            draft.save(update_fields=["status", "sent_by", "sent_at", "message"])
            AuditLog.objects.create(tenant=request.tenant, actor=request.user, action="WHATSAPP_MESSAGE_SENT",
                object_type="WhatsAppMessage", object_id=str(message.id), metadata={"invoice_id": str(draft.invoice_id), "purpose": draft.purpose})
        return Response({"id": str(draft.id), "status": draft.status, "sent_at": draft.sent_at, "provider_message_id": external_id})


class WhatsAppDraftReconcile(APIView):
    permission_classes = [HasTenantMembership]

    @transaction.atomic
    def post(self, request, draft_id):
        if request.membership.role not in FINANCE_ROLES:
            return Response({"error": "Finance role required"}, status=403)
        draft = WhatsAppMessageDraft.objects.select_for_update(of=("self",)).select_related("endpoint", "invoice", "sent_by").filter(
            id=draft_id, tenant=request.tenant).first()
        if not draft:
            return Response({"error": "Message draft not found."}, status=404)
        if draft.status != WhatsAppMessageDraft.Status.SENDING or not draft.send_started_at:
            return Response({"error": "Only a send with an unresolved outcome can be reconciled."}, status=409)
        available_at = draft.send_started_at + WHATSAPP_RECONCILIATION_DELAY
        if timezone.now() < available_at:
            return Response({"error": "Wait five minutes from the send attempt before reconciling its outcome.", "available_at": available_at}, status=409)
        action = request.data.get("action")
        evidence = str(request.data.get("evidence_note", "")).strip()
        if action not in {"confirm_sent", "confirm_not_sent"}:
            return Response({"error": "Choose confirm_sent or confirm_not_sent."}, status=400)
        if len(evidence) < 15 or len(evidence) > 1000:
            return Response({"error": "Record at least 15 characters describing how you checked the Meta delivery outcome."}, status=400)
        actor = request.user
        if action == "confirm_sent":
            external_id = str(request.data.get("provider_message_id", "")).strip()
            if not external_id or len(external_id) > 255:
                return Response({"error": "Enter the WhatsApp message ID shown by Meta."}, status=400)
            existing = WhatsAppMessage.objects.filter(tenant=request.tenant, external_id=external_id).first()
            if existing and (existing.direction != WhatsAppMessage.Direction.OUTBOUND or existing.contact_phone != draft.recipient_phone or existing.endpoint_id != draft.endpoint_id or existing.invoice_id != draft.invoice_id):
                return Response({"error": "That provider message ID is already linked to a different message."}, status=409)
            if existing:
                message = existing
            else:
                message = WhatsAppMessage.objects.create(tenant=request.tenant, endpoint=draft.endpoint,
                    external_id=external_id, contact_phone=draft.recipient_phone, direction=WhatsAppMessage.Direction.OUTBOUND,
                    message_type="template", body=draft.body, status=WhatsAppMessage.Status.SENT,
                    invoice=draft.invoice, sent_by=draft.sent_by or actor,
                    metadata={"purpose": draft.purpose, "manually_reconciled": True})
            draft.status = WhatsAppMessageDraft.Status.SENT
            draft.message = message
            draft.sent_at = message.created_at
            draft.error = ""
            draft.save(update_fields=["status", "message", "sent_at", "error"])
            audit_action = "WHATSAPP_MESSAGE_OUTCOME_CONFIRMED_SENT"
            metadata = {"provider_message_id": external_id, "evidence_note": evidence}
        else:
            draft.status = WhatsAppMessageDraft.Status.FAILED
            draft.error = f"Human reconciled as not sent: {evidence}"[:1000]
            draft.save(update_fields=["status", "error"])
            audit_action = "WHATSAPP_MESSAGE_OUTCOME_CONFIRMED_NOT_SENT"
            metadata = {"evidence_note": evidence}
        AuditLog.objects.create(tenant=request.tenant, actor=actor, action=audit_action,
            object_type="WhatsAppMessageDraft", object_id=str(draft.id),
            metadata={"invoice_id": str(draft.invoice_id), "recipient_phone": draft.recipient_phone, **metadata})
        return Response(WhatsAppDrafts._payload(draft))
