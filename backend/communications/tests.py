import hashlib
import hmac
import json

import pytest
from rest_framework.test import APIClient

from accounts.models import Membership, User
from communications.models import WhatsAppEndpoint, WhatsAppMessage, WhatsAppConsent
from communications.models import WhatsAppMessageDraft
from invoices.models import Invoice
from tenants.models import Tenant


@pytest.mark.django_db
def test_webhook_verifies_signature_and_deduplicates_message(monkeypatch):
    tenant = Tenant.objects.create(name="WhatsApp Co", workspace_key="wa-co")
    WhatsAppEndpoint.objects.create(tenant=tenant, phone_number_id="123456789")
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "test-app-secret")
    payload = {"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": "123456789"},
        "messages": [{"id": "wamid.test-1", "from": "919876543210", "timestamp": "1792300000", "type": "text", "text": {"body": "Invoice attached"}}]}}]}]}
    body = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(b"test-app-secret", body, hashlib.sha256).hexdigest()
    client = APIClient()
    denied = client.post("/api/v1/whatsapp/webhook", body, content_type="application/json")
    assert denied.status_code == 403
    first = client.post("/api/v1/whatsapp/webhook", body, content_type="application/json", HTTP_X_HUB_SIGNATURE_256=signature)
    again = client.post("/api/v1/whatsapp/webhook", body, content_type="application/json", HTTP_X_HUB_SIGNATURE_256=signature)
    assert first.status_code == 200 and again.status_code == 200
    assert WhatsAppMessage.objects.filter(tenant=tenant, external_id="wamid.test-1").count() == 1


@pytest.mark.django_db
def test_vendor_message_draft_requires_consent_and_human_send_action(monkeypatch):
    tenant = Tenant.objects.create(name="WhatsApp Drafts", workspace_key="wa-drafts")
    user = User.objects.create_user(username="finance@wa.test", email="finance@wa.test", password="example-pass")
    Membership.objects.create(tenant=tenant, user=user, role="FINANCE")
    endpoint = WhatsAppEndpoint.objects.create(tenant=tenant, phone_number_id="123456789")
    invoice = Invoice.objects.create(tenant=tenant, invoice_number="WA-1", invoice_total="100.00")
    client = APIClient(); client.force_authenticate(user=user)
    url = "/api/v1/whatsapp/drafts"
    payload = {"endpoint_id": str(endpoint.id), "invoice_id": str(invoice.id), "purpose": "CLARIFICATION",
        "recipient_phone": "+919876543210", "body": "Please clarify invoice WA-1."}
    missing_consent = client.post(url, payload, format="json", HTTP_X_WORKSPACE="wa-drafts")
    assert missing_consent.status_code == 409
    consent = client.post("/api/v1/whatsapp/consents", {"phone": "+919876543210", "action": "opt_in", "evidence_note": "Vendor confirmed by signed email."}, format="json", HTTP_X_WORKSPACE="wa-drafts")
    assert consent.status_code == 201 and consent.data["status"] == "OPTED_IN"
    created = client.post(url, payload, format="json", HTTP_X_WORKSPACE="wa-drafts")
    assert created.status_code == 201
    assert created.data["status"] == "DRAFT"
    inbound = WhatsAppMessage.objects.create(tenant=tenant, endpoint=endpoint, external_id="wamid.inbound-1",
        contact_phone="+919876543210", direction="INBOUND", message_type="text", body="Need help with this bill")
    linked = client.patch(f"/api/v1/whatsapp/messages/{inbound.id}", {"invoice_id": str(invoice.id)}, format="json", HTTP_X_WORKSPACE="wa-drafts")
    assert linked.status_code == 200 and linked.data["invoice_id"] == str(invoice.id)
    inbound.refresh_from_db()
    assert inbound.invoice_id == invoice.id
    monkeypatch.delenv("WHATSAPP_ACCESS_TOKEN", raising=False)
    send = client.post(f"/api/v1/whatsapp/drafts/{created.data['id']}/send", {}, format="json", HTTP_X_WORKSPACE="wa-drafts")
    assert send.status_code == 503


@pytest.mark.django_db
def test_inbound_stop_keyword_revokes_consent_and_blocks_existing_draft(monkeypatch):
    tenant = Tenant.objects.create(name="WhatsApp Opt Out", workspace_key="wa-optout")
    user = User.objects.create_user(username="finance@optout.test", email="finance@optout.test", password="example-pass")
    Membership.objects.create(tenant=tenant, user=user, role="FINANCE")
    endpoint = WhatsAppEndpoint.objects.create(tenant=tenant, phone_number_id="987654321")
    invoice = Invoice.objects.create(tenant=tenant, invoice_number="WA-STOP-1", invoice_total="100.00")
    client = APIClient(); client.force_authenticate(user=user)
    consent = client.post("/api/v1/whatsapp/consents", {"phone": "+919876543210", "action": "opt_in", "evidence_note": "Vendor confirmed by signed email."}, format="json", HTTP_X_WORKSPACE="wa-optout")
    assert consent.status_code == 201
    draft = client.post("/api/v1/whatsapp/drafts", {"endpoint_id": str(endpoint.id), "invoice_id": str(invoice.id),
        "recipient_phone": "+919876543210", "purpose": "CLARIFICATION", "body": "Please clarify invoice WA-STOP-1."}, format="json", HTTP_X_WORKSPACE="wa-optout")
    assert draft.status_code == 201
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "opt-out-secret")
    payload = {"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": "987654321"},
        "messages": [{"id": "wamid.stop-1", "from": "919876543210", "type": "text", "text": {"body": "STOP"}}]}}]}]}
    body = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(b"opt-out-secret", body, hashlib.sha256).hexdigest()
    webhook = APIClient().post("/api/v1/whatsapp/webhook", body, content_type="application/json", HTTP_X_HUB_SIGNATURE_256=signature)
    assert webhook.status_code == 200
    stored = WhatsAppConsent.objects.get(tenant=tenant, phone="+919876543210")
    assert stored.status == WhatsAppConsent.Status.OPTED_OUT and stored.source == WhatsAppConsent.Source.INBOUND_KEYWORD
    blocked = client.post(f"/api/v1/whatsapp/drafts/{draft.data['id']}/send", {}, format="json", HTTP_X_WORKSPACE="wa-optout")
    assert blocked.status_code == 409 and "opted out" in blocked.data["error"]


@pytest.mark.django_db
def test_whatsapp_consent_updates_are_tenant_scoped_and_audited():
    from audit.models import AuditLog
    tenant = Tenant.objects.create(name="Consent tenant", workspace_key="consent-tenant")
    user = User.objects.create_user(username="finance@consent.test", email="finance@consent.test", password="example-pass")
    Membership.objects.create(tenant=tenant, user=user, role="FINANCE")
    client = APIClient(); client.force_authenticate(user=user)
    bad_note = client.post("/api/v1/whatsapp/consents", {"phone": "+919876543210", "action": "opt_in", "evidence_note": "OK"}, format="json", HTTP_X_WORKSPACE="consent-tenant")
    assert bad_note.status_code == 400
    saved = client.post("/api/v1/whatsapp/consents", {"phone": "+919876543210", "action": "opt_in", "evidence_note": "Confirmed during signed vendor onboarding."}, format="json", HTTP_X_WORKSPACE="consent-tenant")
    listed = client.get("/api/v1/whatsapp/consents", HTTP_X_WORKSPACE="consent-tenant")
    assert saved.status_code == 201 and listed.data[0]["phone"] == "+919876543210"
    assert AuditLog.objects.filter(tenant=tenant, action="WHATSAPP_CONSENT_OPTED_IN").count() == 1


@pytest.mark.django_db
def test_stuck_whatsapp_send_can_only_be_reconciled_with_evidence():
    from datetime import timedelta
    from django.utils import timezone
    from audit.models import AuditLog
    tenant = Tenant.objects.create(name="WhatsApp Reconcile", workspace_key="wa-reconcile")
    user = User.objects.create_user(username="finance@reconcile.test", email="finance@reconcile.test", password="example-pass")
    Membership.objects.create(tenant=tenant, user=user, role="FINANCE")
    endpoint = WhatsAppEndpoint.objects.create(tenant=tenant, phone_number_id="567890123")
    invoice = Invoice.objects.create(tenant=tenant, invoice_number="WA-R-1", invoice_total="75.00")
    started_at = timezone.now() - timedelta(minutes=6)
    recent_draft = WhatsAppMessageDraft.objects.create(tenant=tenant, invoice=invoice, endpoint=endpoint,
        recipient_phone="+919876543212", recipient_consent_confirmed=True, purpose="CLARIFICATION", body="Please clarify WA-R-1.",
        status="SENDING", created_by=user, sent_by=user, send_started_at=timezone.now())
    sent_draft = WhatsAppMessageDraft.objects.create(tenant=tenant, invoice=invoice, endpoint=endpoint,
        recipient_phone="+919876543210", recipient_consent_confirmed=True, purpose="CLARIFICATION", body="Please clarify WA-R-1.",
        status="SENDING", created_by=user, sent_by=user, send_started_at=started_at)
    not_sent_draft = WhatsAppMessageDraft.objects.create(tenant=tenant, invoice=invoice, endpoint=endpoint,
        recipient_phone="+919876543211", recipient_consent_confirmed=True, purpose="PAYMENT_REMINDER", body="Payment is due for WA-R-1.",
        status="SENDING", created_by=user, sent_by=user, send_started_at=started_at)
    client = APIClient(); client.force_authenticate(user=user)
    early = client.post(f"/api/v1/whatsapp/drafts/{recent_draft.id}/reconcile", {"action": "confirm_sent", "provider_message_id": "wamid.reconcile-early", "evidence_note": "Found message in Meta manager."}, format="json", HTTP_X_WORKSPACE="wa-reconcile")
    assert early.status_code == 409
    missing_evidence = client.post(f"/api/v1/whatsapp/drafts/{not_sent_draft.id}/reconcile", {"action": "confirm_not_sent", "evidence_note": "No"}, format="json", HTTP_X_WORKSPACE="wa-reconcile")
    assert missing_evidence.status_code == 400
    confirmed_sent = client.post(f"/api/v1/whatsapp/drafts/{sent_draft.id}/reconcile", {"action": "confirm_sent", "provider_message_id": "wamid.reconcile-1", "evidence_note": "Verified message ID in Meta WhatsApp Manager."}, format="json", HTTP_X_WORKSPACE="wa-reconcile")
    assert confirmed_sent.status_code == 200 and confirmed_sent.data["status"] == "SENT"
    message = WhatsAppMessage.objects.get(tenant=tenant, external_id="wamid.reconcile-1")
    assert message.invoice_id == invoice.id and message.metadata["manually_reconciled"] is True
    confirmed_not_sent = client.post(f"/api/v1/whatsapp/drafts/{not_sent_draft.id}/reconcile", {"action": "confirm_not_sent", "evidence_note": "Checked delivery records in Meta Manager; no message was accepted."}, format="json", HTTP_X_WORKSPACE="wa-reconcile")
    assert confirmed_not_sent.status_code == 200 and confirmed_not_sent.data["status"] == "FAILED"
    assert "Checked delivery records" in confirmed_not_sent.data["error"]
    assert AuditLog.objects.filter(tenant=tenant, action="WHATSAPP_MESSAGE_OUTCOME_CONFIRMED_SENT").count() == 1
    assert AuditLog.objects.filter(tenant=tenant, action="WHATSAPP_MESSAGE_OUTCOME_CONFIRMED_NOT_SENT").count() == 1


@pytest.mark.django_db
def test_whatsapp_timeout_keeps_draft_unresolved_instead_of_inviting_duplicate_send(monkeypatch):
    import urllib.error
    from audit.models import AuditLog
    tenant = Tenant.objects.create(name="WhatsApp Timeout", workspace_key="wa-timeout")
    user = User.objects.create_user(username="finance@timeout.test", email="finance@timeout.test", password="example-pass")
    Membership.objects.create(tenant=tenant, user=user, role="FINANCE")
    endpoint = WhatsAppEndpoint.objects.create(tenant=tenant, phone_number_id="987650123")
    invoice = Invoice.objects.create(tenant=tenant, invoice_number="WA-T-1", invoice_total="75.00")
    WhatsAppConsent.objects.create(tenant=tenant, phone="+919876543210", status=WhatsAppConsent.Status.OPTED_IN,
        source=WhatsAppConsent.Source.MANUAL, evidence_note="Verified during supplier onboarding.", updated_by=user)
    draft = WhatsAppMessageDraft.objects.create(tenant=tenant, invoice=invoice, endpoint=endpoint,
        recipient_phone="+919876543210", recipient_consent_confirmed=True, purpose="CLARIFICATION",
        body="Please clarify WA-T-1.", created_by=user)
    monkeypatch.setenv("WHATSAPP_GRAPH_API_VERSION", "v99.0")
    monkeypatch.setenv("WHATSAPP_APPROVED_TEMPLATE", "approved_utility")
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "unit-test-token")
    def timeout(_request, timeout=15): raise urllib.error.URLError("timed out")
    monkeypatch.setattr("communications.views.urllib.request.urlopen", timeout)
    client = APIClient(); client.force_authenticate(user=user)
    response = client.post(f"/api/v1/whatsapp/drafts/{draft.id}/send", {}, format="json", HTTP_X_WORKSPACE="wa-timeout")
    draft.refresh_from_db()
    assert response.status_code == 502
    assert draft.status == WhatsAppMessageDraft.Status.SENDING and draft.send_started_at is not None
    assert "outcome is unknown" in draft.error
    assert AuditLog.objects.filter(tenant=tenant, action="WHATSAPP_MESSAGE_OUTCOME_UNKNOWN", object_id=str(draft.id)).exists()


@pytest.mark.django_db
def test_whatsapp_delivery_callbacks_do_not_downgrade_terminal_states(monkeypatch):
    from audit.models import AuditLog
    tenant = Tenant.objects.create(name="WhatsApp Delivery Order", workspace_key="wa-delivery-order")
    endpoint = WhatsAppEndpoint.objects.create(tenant=tenant, phone_number_id="987650987")
    read_message = WhatsAppMessage.objects.create(tenant=tenant, endpoint=endpoint, external_id="wamid.read-order",
        contact_phone="+919876543210", direction="OUTBOUND", status=WhatsAppMessage.Status.SENT)
    failed_message = WhatsAppMessage.objects.create(tenant=tenant, endpoint=endpoint, external_id="wamid.failed-order",
        contact_phone="+919876543211", direction="OUTBOUND", status=WhatsAppMessage.Status.SENT)
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "delivery-order-secret")
    statuses = [{"id": "wamid.read-order", "status": name} for name in ("delivered", "sent", "read", "failed", "delivered")]
    statuses += [{"id": "wamid.failed-order", "status": name} for name in ("failed", "delivered")]
    payload = {"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": endpoint.phone_number_id}, "statuses": statuses}}]}]}
    body = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(b"delivery-order-secret", body, hashlib.sha256).hexdigest()
    response = APIClient().post("/api/v1/whatsapp/webhook", body, content_type="application/json", HTTP_X_HUB_SIGNATURE_256=signature)
    assert response.status_code == 200
    read_message.refresh_from_db(); failed_message.refresh_from_db()
    assert read_message.status == WhatsAppMessage.Status.READ
    assert failed_message.status == WhatsAppMessage.Status.FAILED
    assert AuditLog.objects.filter(tenant=tenant, action="WHATSAPP_DELIVERY_STATUS_UPDATED").count() == 3
