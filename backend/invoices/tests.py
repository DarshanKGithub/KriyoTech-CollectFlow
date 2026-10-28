from decimal import Decimal
import pytest
from tenants.models import Tenant
from accounts.models import User, Membership
from invoices.models import Invoice
from vendors.models import Vendor
from exports_app.services import create_tally_csv
from rest_framework.test import APIClient
from django.test import override_settings
from invoices.models import DuplicateCheck

@pytest.mark.django_db
def test_tenant_membership_and_export_state():
    tenant = Tenant.objects.create(name="Company", workspace_key="company")
    user = User.objects.create_user(username="owner@test", email="owner@test", password="example-pass")
    Membership.objects.create(tenant=tenant, user=user, role="OWNER")
    vendor = Vendor.objects.create(tenant=tenant, name="Vendor", approved=True)
    invoice = Invoice.objects.create(tenant=tenant, vendor=vendor, invoice_number="INV", status=Invoice.Status.PAYMENT_READY, invoice_total=Decimal("100"))
    job, body = create_tally_csv(tenant, [invoice], user)
    invoice.refresh_from_db()
    assert invoice.status == Invoice.Status.EXPORTED
    assert job.debit_total == job.credit_total == Decimal("100")
    assert "Voucher Type,Invoice Number" in body

@pytest.mark.django_db
def test_invoice_list_is_scoped_to_authenticated_membership():
    first = Tenant.objects.create(name="First", workspace_key="first")
    second = Tenant.objects.create(name="Second", workspace_key="second")
    user = User.objects.create_user(username="member@test", email="member@test", password="example-pass")
    Membership.objects.create(tenant=first, user=user, role="FINANCE")
    Invoice.objects.create(tenant=first, invoice_number="VISIBLE")
    Invoice.objects.create(tenant=second, invoice_number="HIDDEN")
    client = APIClient(); client.force_authenticate(user=user)
    response = client.get("/api/v1/invoices/", HTTP_X_WORKSPACE="first")
    assert response.status_code == 200
    assert [row["invoice_number"] for row in response.data["results"]] == ["VISIBLE"]
    denied = client.get("/api/v1/invoices/", HTTP_X_WORKSPACE="second")
    assert denied.status_code == 403

@pytest.mark.django_db
def test_auditor_can_read_but_cannot_create_invoice():
    tenant = Tenant.objects.create(name="Audit Company", workspace_key="audit-company")
    user = User.objects.create_user(username="auditor@test", email="auditor@test", password="example-pass")
    Membership.objects.create(tenant=tenant, user=user, role="AUDITOR")
    client = APIClient(); client.force_authenticate(user=user)
    response = client.post("/api/v1/invoices/", {"invoice_number": "NOPE"}, format="json", HTTP_X_WORKSPACE="audit-company")
    assert response.status_code == 403

@pytest.mark.django_db
def test_duplicate_review_is_tenant_scoped_and_audited():
    from audit.models import AuditLog
    tenant = Tenant.objects.create(name="Review Company", workspace_key="review-company")
    user = User.objects.create_user(username="finance@test", email="finance@test", password="example-pass")
    Membership.objects.create(tenant=tenant, user=user, role="FINANCE")
    current = Invoice.objects.create(tenant=tenant, invoice_number="CURRENT")
    candidate = Invoice.objects.create(tenant=tenant, invoice_number="OLDER")
    check = DuplicateCheck.objects.create(tenant=tenant, invoice=current, candidate_invoice=candidate, kind="EXACT", score=1)
    client = APIClient(); client.force_authenticate(user=user)
    response = client.post(f"/api/v1/duplicate-checks/{check.id}/decision", {"decision": "NOT_DUPLICATE", "note": "Different period"}, format="json", HTTP_X_WORKSPACE="review-company")
    assert response.status_code == 200
    check.refresh_from_db(); current.refresh_from_db()
    assert check.decision == "NOT_DUPLICATE"
    assert current.duplicate_review_complete is True
    assert AuditLog.objects.filter(tenant=tenant, action="DUPLICATE_REVIEWED").count() == 1

@pytest.mark.django_db
def test_matching_controls_validate_and_persist_changes():
    tenant = Tenant.objects.create(name="Controls Company", workspace_key="controls")
    user = User.objects.create_user(username="owner@controls.test", email="owner@controls.test", password="example-pass")
    Membership.objects.create(tenant=tenant, user=user, role="OWNER")
    client = APIClient(); client.force_authenticate(user=user)
    path = "/api/v1/matching/settings"
    good = client.patch(path, {"rate_tolerance_percent": "2.5", "matching_priority": ["GSTIN", "ALIAS"]}, format="json", HTTP_X_WORKSPACE="controls")
    bad = client.patch(path, {"tax_tolerance_percent": "101"}, format="json", HTTP_X_WORKSPACE="controls")
    assert good.status_code == 200 and Decimal(str(good.data["rate_tolerance_percent"])) == Decimal("2.5")
    assert bad.status_code == 400

@pytest.mark.django_db
def test_payment_requires_exact_allocation_and_updates_invoice_balance():
    tenant = Tenant.objects.create(name="Payments Company", workspace_key="payments")
    user = User.objects.create_user(username="pay@company.test", email="pay@company.test", password="example-pass")
    Membership.objects.create(tenant=tenant, user=user, role="FINANCE")
    vendor = Vendor.objects.create(tenant=tenant, name="Vendor", approved=True)
    invoice = Invoice.objects.create(tenant=tenant, vendor=vendor, invoice_number="PAY-1", invoice_total=Decimal("100"), status=Invoice.Status.PAYMENT_READY)
    client = APIClient(); client.force_authenticate(user=user)
    payload = {"vendor": str(vendor.id), "amount": "100.00", "paid_at": "2026-10-18", "mode": "BANK_TRANSFER", "reference_number": "UTR-1", "allocations": [{"invoice": str(invoice.id), "amount": "100.00"}]}
    response = client.post("/api/v1/payments", payload, format="json", HTTP_X_WORKSPACE="payments")
    assert response.status_code == 201, response.data
    invoice.refresh_from_db()
    assert invoice.payment_status == "PAID"
    assert invoice.payment_allocations.count() == 1


@pytest.mark.django_db(transaction=True)
def test_invoice_upload_extraction_approval_and_payment_workflow(tmp_path, monkeypatch):
    from django.core.files.uploadedfile import SimpleUploadedFile
    from invoices.models import ExtractionResult
    from matching.models import MatchResult
    from invoices.tasks import extract_invoice
    from payments.models import Payment

    tenant = Tenant.objects.create(name="Invoice workflow", workspace_key="invoice-workflow")
    finance = User.objects.create_user(username="upload@workflow.test", email="upload@workflow.test", password="example-pass")
    approver = User.objects.create_user(username="approve@workflow.test", email="approve@workflow.test", password="example-pass")
    Membership.objects.create(tenant=tenant, user=finance, role="FINANCE")
    Membership.objects.create(tenant=tenant, user=approver, role="APPROVER")
    vendor = Vendor.objects.create(tenant=tenant, name="Workflow Vendor", approved=True)
    client = APIClient(); client.force_authenticate(user=finance)

    class FakeProvider:
        def extract(self, document):
            return {"fields": {"supplier_name": "Workflow Vendor", "invoice_number": "WF-INV-1", "invoice_date": "2026-10-01", "invoice_total": "118.00"}, "confidence": {"supplier_name": 0.99, "invoice_number": 0.99, "invoice_date": 0.99, "invoice_total": 0.99}, "lines": []}

    monkeypatch.setattr("invoices.tasks.get_extraction_provider", lambda: FakeProvider())
    monkeypatch.setattr("invoices.tasks.extract_invoice.delay", lambda *args, **kwargs: None)
    # Keep this workflow acceptance check focused on extraction/approval/payment;
    # subscription entitlement is covered by the admin access-control tests.
    monkeypatch.setattr("admin_console.services.has_feature", lambda tenant, feature: True)
    with override_settings(EXTRACTION_PROVIDER="test-provider", MEDIA_ROOT=tmp_path, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
        uploaded = client.post("/api/v1/invoices/", {"file": SimpleUploadedFile("workflow.pdf", b"%PDF-1.4 workflow test", content_type="application/pdf")}, format="multipart", HTTP_X_WORKSPACE=tenant.workspace_key)
        assert uploaded.status_code == 201, uploaded.data
        invoice_id = uploaded.data["id"]
        queued = ExtractionResult.objects.get(invoice_id=invoice_id)
        assert queued.status == "QUEUED"
        extracted = extract_invoice(str(invoice_id), str(queued.id))
        assert extracted["status"] == "COMPLETED"
        invoice = Invoice.objects.get(id=invoice_id)
        assert invoice.invoice_number == "WF-INV-1" and invoice.invoice_total == Decimal("118.00")

        # The matching decision is represented by a persisted result so the test
        # exercises the real approval and payment endpoints after extraction.
        invoice.vendor = vendor
        invoice.status = Invoice.Status.MATCHED
        invoice.save(update_fields=["vendor", "status"])
        MatchResult.objects.create(tenant=tenant, invoice=invoice, run_number=1, outcome="MATCHED")
        submitted = client.post(f"/api/v1/invoices/{invoice_id}/submit-for-approval/", {}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
        assert submitted.status_code == 200 and submitted.data["status"] == Invoice.Status.APPROVAL_PENDING, submitted.data
        approver_client = APIClient(); approver_client.force_authenticate(user=approver)
        approved = approver_client.post(f"/api/v1/invoices/{invoice_id}/approve/", {}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
        assert approved.status_code == 200 and approved.data["status"] == Invoice.Status.PAYMENT_READY, approved.data
        paid = client.post("/api/v1/payments", {"vendor": str(vendor.id), "amount": "118.00", "paid_at": "2026-10-19", "mode": "BANK_TRANSFER", "reference_number": "WF-UTR-1", "allocations": [{"invoice": str(invoice_id), "amount": "118.00"}]}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
        assert paid.status_code == 201, paid.data
        invoice.refresh_from_db()
        assert invoice.payment_status == "PAID"
        assert Payment.objects.filter(tenant=tenant, allocations__invoice=invoice).count() == 1

@pytest.mark.django_db
def test_inbound_email_is_authenticated_and_idempotent():
    from django.core.files.uploadedfile import SimpleUploadedFile
    from inbound_email.models import EmailIngestionLog
    tenant = Tenant.objects.create(name="Inbox Company", workspace_key="inbox", invoice_intake_token="intake-token")
    path = "/api/v1/email-ingestion/inbox"
    client = APIClient()
    denied = client.post(path, {"message_id": "msg-1"}, format="multipart")
    assert denied.status_code == 401
    file = SimpleUploadedFile("invoice.pdf", b"%PDF fake test bytes", content_type="application/pdf")
    response = client.post(path, {"message_id": "msg-1", "sender": "ap@supplier.test", "attachments": file}, format="multipart", HTTP_X_INVOICE_INTAKE_TOKEN="intake-token")
    assert response.status_code == 202
    repeat = client.post(path, {"message_id": "msg-1"}, format="multipart", HTTP_X_INVOICE_INTAKE_TOKEN="intake-token")
    assert repeat.status_code == 200 and repeat.data["duplicate_delivery"] is True
    assert EmailIngestionLog.objects.filter(tenant=tenant, message_id="msg-1").count() == 1
    assert Invoice.objects.filter(tenant=tenant, source_email__message_id="msg-1").count() == 1

@pytest.mark.django_db
def test_inbound_email_accepts_multiple_supported_files_and_quarantines_unsupported_file():
    from django.core.files.uploadedfile import SimpleUploadedFile
    from inbound_email.models import EmailIngestionLog
    from documents.models import Document
    tenant = Tenant.objects.create(name="Multi Attachment Co", workspace_key="multi-inbox", invoice_intake_token="secret-intake")
    client = APIClient()
    response = client.post("/api/v1/email-ingestion/multi-inbox", {
        "message_id": "multi-1",
        "attachments": [
            SimpleUploadedFile("invoice.pdf", b"%PDF one", content_type="application/pdf"),
            SimpleUploadedFile("invoice.jpg", b"fake jpeg", content_type="image/jpeg"),
            SimpleUploadedFile("payload.exe", b"not an invoice", content_type="application/octet-stream"),
        ],
    }, format="multipart", HTTP_X_INVOICE_INTAKE_TOKEN="secret-intake")
    assert response.status_code == 202, response.data
    assert response.data["status"] == EmailIngestionLog.Status.PARTIAL
    assert len(response.data["attachments"]) == 3
    assert sum(row["status"] != "QUARANTINED" for row in response.data["attachments"]) == 2
    assert sum(row["status"] == "QUARANTINED" for row in response.data["attachments"]) == 1
    assert Document.objects.filter(tenant=tenant).count() == 2
    assert Invoice.objects.filter(tenant=tenant, source_email__message_id="multi-1").count() == 2

@pytest.mark.django_db
def test_rule_driven_approval_requires_each_ordered_step():
    from matching.models import MatchResult
    tenant = Tenant.objects.create(name="Rules Company", workspace_key="rules")
    submitter = User.objects.create_user(username="submit@rules.test", email="submit@rules.test", password="example-pass")
    approver = User.objects.create_user(username="approver@rules.test", email="approver@rules.test", password="example-pass")
    finance = User.objects.create_user(username="finance@rules.test", email="finance@rules.test", password="example-pass")
    Membership.objects.create(tenant=tenant, user=submitter, role="FINANCE")
    Membership.objects.create(tenant=tenant, user=approver, role="APPROVER")
    Membership.objects.create(tenant=tenant, user=finance, role="FINANCE")
    vendor = Vendor.objects.create(tenant=tenant, name="Rules Supplier", approved=True)
    invoice = Invoice.objects.create(tenant=tenant, vendor=vendor, invoice_number="RULE-1", invoice_total=Decimal("50"), status=Invoice.Status.MATCHED, uploaded_by=submitter)
    MatchResult.objects.create(tenant=tenant, invoice=invoice, run_number=1, outcome="MATCHED")
    from approvals.models import ApprovalRule
    ApprovalRule.objects.create(tenant=tenant, name="Two eyes", conditions={}, steps=[{"role": "APPROVER"}, {"role": "FINANCE"}])
    client = APIClient(); client.force_authenticate(user=submitter)
    submitted = client.post(f"/api/v1/invoices/{invoice.id}/submit-for-approval/", {}, format="json", HTTP_X_WORKSPACE="rules")
    assert submitted.status_code == 200
    client.force_authenticate(user=approver)
    first = client.post(f"/api/v1/invoices/{invoice.id}/approve/", {}, format="json", HTTP_X_WORKSPACE="rules")
    assert first.status_code == 200 and first.data["status"] == "APPROVAL_PENDING"
    client.force_authenticate(user=finance)
    second = client.post(f"/api/v1/invoices/{invoice.id}/approve/", {}, format="json", HTTP_X_WORKSPACE="rules")
    assert second.status_code == 200 and second.data["status"] == "PAYMENT_READY"

@pytest.mark.django_db
def test_bulk_exception_action_requires_preview_token_and_audit():
    from exceptions_app.models import InvoiceException
    from audit.models import AuditLog
    tenant = Tenant.objects.create(name="Bulk Company", workspace_key="bulk")
    user = User.objects.create_user(username="finance@bulk.test", email="finance@bulk.test", password="example-pass")
    Membership.objects.create(tenant=tenant, user=user, role="FINANCE")
    invoice = Invoice.objects.create(tenant=tenant, invoice_number="B-1", status=Invoice.Status.EXCEPTION)
    exc = InvoiceException.objects.create(tenant=tenant, invoice=invoice, code="RATE_VARIANCE")
    client = APIClient(); client.force_authenticate(user=user)
    preview = client.post("/api/v1/bulk-jobs", {"operation": "RESOLVE_EXCEPTIONS", "ids": [str(exc.id)], "resolution_note": "Verified against supplier amendment"}, format="json", HTTP_X_WORKSPACE="bulk")
    assert preview.status_code == 201
    committed = client.post(f"/api/v1/bulk-jobs/{preview.data['id']}/commit", {"preview_token": preview.data["preview_token"]}, format="json", HTTP_X_WORKSPACE="bulk")
    assert committed.status_code == 200
    exc.refresh_from_db(); invoice.refresh_from_db()
    assert exc.status == "RESOLVED" and invoice.status == "MATCHED"
    assert AuditLog.objects.filter(tenant=tenant, action="BULK_RESOLVE_EXCEPTIONS").count() == 1

@pytest.mark.django_db
def test_exception_sla_applies_deadline_and_overdue_escalation_notifies_owner():
    from datetime import timedelta
    from django.utils import timezone
    from exceptions_app.models import ExceptionSLA, InvoiceException
    from notifications.models import Notification
    tenant = Tenant.objects.create(name="SLA Company", workspace_key="sla")
    user = User.objects.create_user(username="owner@sla.test", email="owner@sla.test", password="example-pass")
    Membership.objects.create(tenant=tenant, user=user, role="OWNER")
    ExceptionSLA.objects.create(tenant=tenant, exception_code="RATE_VARIANCE", due_after_hours=1, priority="HIGH", escalation_roles=["OWNER"])
    invoice = Invoice.objects.create(tenant=tenant, invoice_number="SLA-1")
    exc = InvoiceException.objects.create(tenant=tenant, invoice=invoice, code="RATE_VARIANCE")
    exc.refresh_from_db()
    assert exc.sla_due_at is not None
    InvoiceException.objects.filter(id=exc.id).update(sla_due_at=timezone.now()-timedelta(minutes=1))
    client = APIClient(); client.force_authenticate(user=user)
    response = client.post("/api/v1/exceptions/escalate-overdue", {}, format="json", HTTP_X_WORKSPACE="sla")
    assert response.status_code == 200 and response.data["escalated"] == 1
    assert Notification.objects.filter(tenant=tenant, recipient=user, payload__title="Exception escalated").exists()

@pytest.mark.django_db
def test_custom_field_values_validate_types_and_are_tenant_scoped():
    from invoices.models import CustomFieldDefinition
    tenant = Tenant.objects.create(name="Fields Company", workspace_key="fields")
    user = User.objects.create_user(username="owner@fields.test", email="owner@fields.test", password="example-pass")
    Membership.objects.create(tenant=tenant, user=user, role="OWNER")
    invoice = Invoice.objects.create(tenant=tenant, invoice_number="F-1")
    field = CustomFieldDefinition.objects.create(tenant=tenant, name="Cost centre", key="cost_centre", field_type="CHOICE", options=["OPS", "SALES"], required=True)
    client = APIClient(); client.force_authenticate(user=user)
    path = f"/api/v1/invoices/{invoice.id}/custom-fields"
    valid = client.patch(path, {field.key: "OPS"}, format="json", HTTP_X_WORKSPACE="fields")
    invalid = client.patch(path, {field.key: "FINANCE"}, format="json", HTTP_X_WORKSPACE="fields")
    assert valid.status_code == 200 and valid.data[field.key]["value"] == "OPS"
    assert invalid.status_code == 400

@pytest.mark.django_db
def test_credit_note_cannot_reduce_payable_below_allocated_payment():
    from payments.models import Payment, PaymentAllocation, CreditDebitNote
    from invoices.phase2 import invoice_net_payable
    from datetime import date
    tenant = Tenant.objects.create(name="Notes Company", workspace_key="notes")
    creator = User.objects.create_user(username="maker@notes.test", email="maker@notes.test", password="example-pass")
    approver = User.objects.create_user(username="checker@notes.test", email="checker@notes.test", password="example-pass")
    Membership.objects.create(tenant=tenant, user=creator, role="FINANCE")
    Membership.objects.create(tenant=tenant, user=approver, role="OWNER")
    invoice = Invoice.objects.create(tenant=tenant, invoice_number="N-1", invoice_total=Decimal("100"))
    payment = Payment.objects.create(tenant=tenant, amount=Decimal("80"), paid_at=date.today(), created_by=creator)
    PaymentAllocation.objects.create(tenant=tenant, payment=payment, invoice=invoice, amount=Decimal("80"))
    note = CreditDebitNote.objects.create(tenant=tenant, invoice=invoice, kind="CREDIT", note_number="CN-1", amount=Decimal("30"), reason="DISCOUNT", created_by=creator)
    client = APIClient(); client.force_authenticate(user=approver)
    response = client.post(f"/api/v1/credit-debit-notes/{note.id}/decision", {"decision": "APPROVED"}, format="json", HTTP_X_WORKSPACE="notes")
    assert response.status_code == 409
    assert invoice_net_payable(invoice) == Decimal("100")
