from decimal import Decimal
import pytest
from django.db import connection
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient
from accounts.models import Membership, User, BranchMembership
from invoices.models import Invoice, InvoiceLine
from payments.models import Payment
from settlements.models import SourceAccount
from tenants.models import Tenant, Branch
from vendors.models import Vendor
from procurement.models import PurchaseOrder, PurchaseOrderLine, GRN, GRNLine
from .models import BankStatement, BankTransaction, TaxReview, VendorPortalInvite, AIReviewSuggestion, TenantAPIKey, WebhookEndpoint, WebhookDelivery, GmailConnection
from admin_console.models import Feature, Plan, PlanFeature, Subscription


@pytest.fixture
def finance_client(db):
    tenant = Tenant.objects.create(name="Phase 3 Co", workspace_key="phase3-co")
    user = User.objects.create_user(username="finance@p3.test", email="finance@p3.test", password="example-pass")
    Membership.objects.create(tenant=tenant, user=user, role="FINANCE")
    client = APIClient(); client.force_authenticate(user=user)
    return tenant, user, client


@pytest.mark.django_db
def test_tax_review_scoped_and_audited(finance_client):
    from audit.models import AuditLog
    tenant, user, client = finance_client
    invoice = Invoice.objects.create(tenant=tenant, invoice_number="TAX-1", supplier_gstin="27ABCDE1234F1Z5", taxable_total="100", gst_total="18", tds_total="0", invoice_total="118")
    other = Tenant.objects.create(name="Other", workspace_key="other-p3")
    hidden = Invoice.objects.create(tenant=other, invoice_number="HIDDEN")
    response = client.patch("/api/v1/compliance/tax-reviews", {"invoice_id": str(invoice.id), "itc_eligible": True, "tds_section": "194C", "tds_rate": "1.000"}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert response.status_code == 200
    review = TaxReview.objects.get(invoice=invoice)
    assert review.reviewed_by == user and review.gstin_valid_format is True
    denied = client.patch("/api/v1/compliance/tax-reviews", {"invoice_id": str(hidden.id), "itc_eligible": True}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert denied.status_code == 404
    assert AuditLog.objects.filter(tenant=tenant, action="TAX_REVIEW_UPDATED").count() == 1


@pytest.mark.django_db
def test_workspace_login_discovers_companies_and_self_signup_is_disabled(finance_client):
    tenant, user, client = finance_client
    other = Tenant.objects.create(name="Second company", workspace_key="second-company")
    Membership.objects.create(tenant=other, user=user, role="AUDITOR")
    workspaces = client.get("/api/v1/auth/workspaces")
    assert workspaces.status_code == 200
    assert {row["workspace_key"] for row in workspaces.data} == {tenant.workspace_key, other.workspace_key}
    assert client.post("/api/v1/auth/register-company", {"company_name": "Self Signup", "email": "new@p3.test", "password": "a-secure-password"}, format="json").status_code == 404


@pytest.mark.django_db
def test_branch_creation_assignment_and_tenant_isolation(finance_client):
    from django.core.exceptions import ValidationError
    tenant, owner, client = finance_client
    # Upgrade the fixture membership to owner; branch administration is owner-only.
    Membership.objects.filter(tenant=tenant, user=owner).update(role="OWNER")
    branch_response = client.post("/api/v1/branches", {"name": "Mumbai office", "code": "mumbai"}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert branch_response.status_code == 201, branch_response.data
    branch = Branch.objects.get(id=branch_response.data["id"])
    member = User.objects.create_user(username="branch-user@p3.test", email="branch-user@p3.test", password="example-pass")
    membership = Membership.objects.create(tenant=tenant, user=member, role="FINANCE")
    assigned = client.post("/api/v1/branch-assignments", {"membership_id": str(membership.id), "branch_id": str(branch.id)}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert assigned.status_code == 200 and assigned.data["assigned"] is True
    assert BranchMembership.objects.get(membership=membership, branch=branch, is_active=True)
    outsider = Tenant.objects.create(name="Branch outsider", workspace_key="branch-outsider")
    hidden_branch = Branch.objects.get(tenant=outsider, is_default=True)
    denied = client.post("/api/v1/branch-assignments", {"membership_id": str(membership.id), "branch_id": str(hidden_branch.id)}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert denied.status_code == 404
    with pytest.raises(ValidationError):
        BranchMembership.objects.create(membership=membership, branch=hidden_branch)
    listed = client.get("/api/v1/branches", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert listed.status_code == 200 and any(row["id"] == str(branch.id) for row in listed.data["branches"])


@pytest.mark.django_db
def test_bank_csv_import_is_atomic_idempotent_and_manually_reconciled(finance_client):
    tenant, user, client = finance_client
    account = SourceAccount.objects.create(tenant=tenant, scope="TENANT", name="Bank", kind="BANK", provider="BANK", external_reference="bank", currency="INR")
    content = b"date,description,reference,amount\n2026-10-18,Vendor transfer,UTR-55,-125.00\n"
    upload = SimpleUploadedFile("statement.csv", content, content_type="text/csv")
    response = client.post("/api/v1/bank-reconciliation", {"file": upload, "account_id": str(account.pk)}, format="multipart", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert response.status_code == 201, response.data
    tx = BankTransaction.objects.get(tenant=tenant)
    assert tx.status == "UNMATCHED" and tx.amount == Decimal("-125.00")
    repeated = SimpleUploadedFile("statement.csv", content, content_type="text/csv")
    again = client.post("/api/v1/bank-reconciliation", {"file": repeated, "account_id": str(account.pk)}, format="multipart", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert again.status_code == 200 and again.data["duplicate_import"] is True
    vendor = Vendor.objects.create(tenant=tenant, name="Supplier", approved=True)
    payment = Payment.objects.create(tenant=tenant, vendor=vendor, source_account=account, currency="INR", amount="125.00", paid_at="2026-10-18", reference_number="UTR-55", created_by=user)
    other_tenant = Tenant.objects.create(name="Bank match isolation", workspace_key="bank-isolation")
    other_vendor = Vendor.objects.create(tenant=other_tenant, name="Supplier", approved=True)
    Payment.objects.create(tenant=other_tenant, vendor=other_vendor, amount="125.00", paid_at="2026-10-18", reference_number="UTR-55")
    suggestions = client.get(f"/api/v1/bank-reconciliation?suggestions_for={tx.id}", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert suggestions.status_code == 200 and len(suggestions.data["suggestions"]) == 1
    assert suggestions.data["suggestions"][0]["payment_id"] == str(payment.id)
    assert suggestions.data["suggestions"][0]["confidence"] == "HIGH"
    assert BankTransaction.objects.get(id=tx.id).status == "UNMATCHED"
    matched = client.patch("/api/v1/bank-reconciliation", {"transaction_id": str(tx.id), "action": "match", "payment_id": str(payment.id)}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert matched.status_code == 200 and matched.data["status"] == "MATCHED"
    confirmed = client.patch("/api/v1/bank-reconciliation", {"transaction_id": str(tx.id), "action": "reconcile"}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert confirmed.status_code == 200 and confirmed.data["status"] == "RECONCILED"


@pytest.mark.django_db
def test_invalid_bank_csv_does_not_create_partial_statement(finance_client):
    tenant, _, client = finance_client
    content = b"date,description,amount\n2026-10-18,Valid,50\nnot-a-date,Bad,20\n"
    upload = SimpleUploadedFile("bad.csv", content, content_type="text/csv")
    response = client.post("/api/v1/bank-reconciliation", {"file": upload}, format="multipart", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert response.status_code == 400
    assert tenant.bankstatement_set.count() == 0


@pytest.mark.django_db
def test_test_bank_feed_is_labeled_idempotent_and_finance_only(finance_client, monkeypatch):
    from audit.models import AuditLog
    from phase3.tasks import build_bank_reconciliation_suggestions

    tenant, user, finance_client = finance_client
    monkeypatch.setattr(build_bank_reconciliation_suggestions, "delay", lambda *args, **kwargs: None)
    first = finance_client.post("/api/v1/bank-reconciliation", {"action": "generate_test_feed"},
        format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert first.status_code == 201, first.data
    statement = BankStatement.objects.get(pk=first.data["id"])
    assert statement.is_test_data is True
    assert statement.provenance_note.startswith("SIMULATED TEST BANK DATA")
    assert statement.transactions.count() == 4
    rows = finance_client.get("/api/v1/bank-reconciliation", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert rows.status_code == 200
    assert all(row["is_test_data"] is True for row in rows.data["transactions"])
    again = finance_client.post("/api/v1/bank-reconciliation", {"action": "generate_test_feed"},
        format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert again.status_code == 200 and again.data["duplicate_import"] is True
    assert BankStatement.objects.filter(tenant=tenant, is_test_data=True).count() == 1
    assert AuditLog.objects.filter(tenant=tenant, action="TEST_BANK_FEED_GENERATED").count() == 1

    Membership.objects.filter(tenant=tenant, user=user).update(role="APPROVER")
    denied = finance_client.post("/api/v1/bank-reconciliation", {"action": "generate_test_feed"},
        format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert denied.status_code == 403


@pytest.mark.django_db
def test_reconciliation_role_matrix_and_branch_scope(finance_client, monkeypatch):
    from phase3.tasks import build_bank_reconciliation_suggestions

    tenant, _, _ = finance_client
    monkeypatch.setattr(build_bank_reconciliation_suggestions, "delay", lambda *args, **kwargs: None)
    expectations = {
        "OWNER": (200, True), "FINANCE": (200, True), "AUDITOR": (200, False),
        "APPROVER": (403, False), "PURCHASE": (403, False), "STORE": (403, False),
        "FLEET": (403, False), "DRIVER": (403, False),
    }
    for role, (read_status, can_write) in expectations.items():
        user = User.objects.create_user(username=f"{role.lower()}-bank@p3.test",
            email=f"{role.lower()}-bank@p3.test", password="example-pass")
        Membership.objects.create(tenant=tenant, user=user, role=role)
        client = APIClient(); client.force_authenticate(user=user)
        assert client.get("/api/v1/bank-reconciliation", HTTP_X_WORKSPACE=tenant.workspace_key).status_code == read_status, role
        write = client.post("/api/v1/bank-reconciliation", {"action": "generate_test_feed"},
            format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
        assert (write.status_code in {200, 201}) if can_write else (write.status_code == 403), role

    finance_member = Membership.objects.get(tenant=tenant, user__email="finance@p3.test")
    branch, _ = Branch.objects.get_or_create(tenant=tenant, code="main",
        defaults={"name": "Main", "active": True, "is_default": True})
    BranchMembership.objects.create(membership=finance_member, branch=branch, is_active=True)
    finance_member.branch_scope_enabled = True
    finance_member.save(update_fields=["branch_scope_enabled"])
    finance_client = APIClient(); finance_client.force_authenticate(user=finance_member.user)
    assert finance_client.get("/api/v1/bank-reconciliation", HTTP_X_WORKSPACE=tenant.workspace_key).status_code == 403
    assert finance_client.get("/api/v1/invoices/", HTTP_X_WORKSPACE=tenant.workspace_key).status_code == 403
    assigned_branches = finance_client.get("/api/v1/branches", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert assigned_branches.status_code == 200
    assert [row["id"] for row in assigned_branches.data["branches"]] == [str(branch.id)]


@pytest.mark.django_db
def test_daily_digest_is_deduplicated_and_role_scoped(finance_client):
    from fleet.models import FleetFollowUp
    from notifications.models import Notification
    from phase3.tasks import send_daily_operations_digest

    tenant, finance_user, _ = finance_client
    owner = User.objects.create_user(username="owner-digest@p3.test", email="owner-digest@p3.test", password="example-pass")
    fleet = User.objects.create_user(username="fleet-digest@p3.test", email="fleet-digest@p3.test", password="example-pass")
    Membership.objects.create(tenant=tenant, user=owner, role="OWNER")
    Membership.objects.create(tenant=tenant, user=fleet, role="FLEET")
    Invoice.objects.create(tenant=tenant, invoice_number="DIGEST-1", status=Invoice.Status.APPROVAL_PENDING)
    FleetFollowUp.objects.create(tenant=tenant, category="MISSING_POD", description="Add delivery proof")

    result = send_daily_operations_digest.run()
    assert result["digests_created"] == 3
    owner_digest = Notification.objects.get(tenant=tenant, recipient=owner, payload__category="daily_digest")
    finance_digest = Notification.objects.get(tenant=tenant, recipient=finance_user, payload__category="daily_digest")
    fleet_digest = Notification.objects.get(tenant=tenant, recipient=fleet, payload__category="daily_digest")
    assert owner_digest.payload["counts"]["approvals"] == 1
    assert "approvals" not in fleet_digest.payload["counts"]
    assert fleet_digest.payload["counts"]["fleet_followups"] == 1
    assert send_daily_operations_digest.run()["digests_created"] == 0


@pytest.mark.django_db
def test_bank_reconciliation_matches_customer_collections_and_driver_payments(finance_client):
    from datetime import date
    from fleet.models import (DriverSalaryPayment, DriverSalaryRecord, FleetCustomer,
        FleetDriver, FleetTrip, FleetVehicle, TransportCollection, TransportInvoice, TransportOrder)

    tenant, user, client = finance_client
    account = SourceAccount.objects.create(tenant=tenant, scope="TENANT", name="Bank", kind="BANK", provider="BANK", external_reference="bank", currency="INR")
    customer = FleetCustomer.objects.create(tenant=tenant, name="Northwind Customer")
    vehicle = FleetVehicle.objects.create(tenant=tenant, registration_number="MH01AA1234", normalized_registration="MH01AA1234")
    driver = FleetDriver.objects.create(tenant=tenant, name="Asha Driver")
    order = TransportOrder.objects.create(tenant=tenant, order_number="ORD-BANK-1", customer=customer, origin="Pune", destination="Mumbai")
    trip = FleetTrip.objects.create(tenant=tenant, trip_number="TRIP-BANK-1", vehicle=vehicle, driver=driver)
    invoice = TransportInvoice.objects.create(tenant=tenant, customer=customer, order=order, trip=trip, invoice_number="TI-BANK-1", amount="500.00", status="ISSUED")
    collection = TransportCollection.objects.create(tenant=tenant, source_account=account, currency="INR", invoice=invoice, amount="500.00", received_date=date.today(), reference="COLL-500")
    salary = DriverSalaryRecord.objects.create(tenant=tenant, driver=driver, period_start=date.today().replace(day=1), salary_amount="300.00", status="APPROVED", created_by=user)
    salary_payment = DriverSalaryPayment.objects.create(tenant=tenant, source_account=account, currency="INR", salary_record=salary, amount="300.00", payment_date=date.today(), payment_reference="SAL-300", created_by=user)
    statement = BankStatement.objects.create(tenant=tenant, source_account=account, currency="INR", filename="mixed.csv", content_hash="mixed-customer-driver", imported_by=user)
    customer_tx = BankTransaction.objects.create(tenant=tenant, statement=statement, transaction_date=date.today(), description="Northwind Customer receipt", reference="COLL-500", amount="500.00", fingerprint="fingerprint-customer")
    salary_tx = BankTransaction.objects.create(tenant=tenant, statement=statement, transaction_date=date.today(), description="Asha Driver salary", reference="SAL-300", amount="-300.00", fingerprint="fingerprint-salary")

    for tx, target_type, target in ((customer_tx, "CUSTOMER_COLLECTION", collection), (salary_tx, "DRIVER_SALARY_PAYMENT", salary_payment)):
        suggestions = client.get(f"/api/v1/bank-reconciliation?suggestions_for={tx.id}", HTTP_X_WORKSPACE=tenant.workspace_key)
        assert suggestions.status_code == 200, suggestions.data
        assert any(row["target_type"] == target_type and row["target_id"] == str(target.id) for row in suggestions.data["suggestions"])
        matched = client.patch("/api/v1/bank-reconciliation", {"transaction_id": str(tx.id), "action": "match", "target_type": target_type, "target_id": str(target.id)}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
        assert matched.status_code == 200 and matched.data["status"] == "MATCHED", matched.data
        reconciled = client.patch("/api/v1/bank-reconciliation", {"transaction_id": str(tx.id), "action": "reconcile"}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
        assert reconciled.status_code == 200 and reconciled.data["status"] == "RECONCILED", reconciled.data


@pytest.mark.django_db
def test_fleet_role_cannot_disburse_salary_or_approve_salary(finance_client):
    from datetime import date
    from fleet.models import DriverSalaryRecord, FleetDriver

    tenant, owner, _ = finance_client
    driver = FleetDriver.objects.create(tenant=tenant, name="Restricted Driver")
    record = DriverSalaryRecord.objects.create(tenant=tenant, driver=driver, period_start=date.today().replace(day=1), salary_amount="250.00", status="SUBMITTED", submitted_by=owner)
    fleet_user = User.objects.create_user(username="fleet-role@p3.test", email="fleet-role@p3.test", password="example-pass")
    Membership.objects.create(tenant=tenant, user=fleet_user, role="FLEET")
    fleet_client = APIClient(); fleet_client.force_authenticate(user=fleet_user)
    pay = fleet_client.post(f"/api/v1/fleet/driver-salaries/{record.id}/payments", {"amount": "250.00"}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    approve = fleet_client.post(f"/api/v1/fleet/driver-salaries/{record.id}/approve", {}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert pay.status_code == 403
    assert approve.status_code == 403


@pytest.mark.django_db
def test_purchase_order_approval_and_quality_tracked_receipt(finance_client):
    tenant, _, client = finance_client
    vendor = Vendor.objects.create(tenant=tenant, name="PO supplier", approved=True)
    buyer = User.objects.create_user(username="buyer@p3.test", email="buyer@p3.test", password="example-pass")
    Membership.objects.create(tenant=tenant, user=buyer, role="PURCHASE")
    buyer_client = APIClient(); buyer_client.force_authenticate(user=buyer)
    created = buyer_client.post("/api/v1/purchase-orders", {"vendor_id": str(vendor.id), "number": "PO-P3-1", "order_date": "2026-10-18", "lines": [{"description": "Parts", "quantity": "10", "rate": "25.00"}]}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert created.status_code == 201, created.data
    po = PurchaseOrder.objects.get(id=created.data["id"])
    submitted = buyer_client.patch("/api/v1/purchase-orders", {"purchase_order_id": str(po.id), "action": "submit"}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert submitted.status_code == 200 and submitted.data["status"] == "PENDING_APPROVAL"
    approved = client.patch("/api/v1/purchase-orders", {"purchase_order_id": str(po.id), "action": "approve"}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert approved.status_code == 200 and approved.data["status"] == "APPROVED"
    line = PurchaseOrderLine.objects.get(purchase_order=po)
    received = client.post("/api/v1/grns", {"purchase_order_id": str(po.id), "number": "GRN-P3-1", "received_at": "2026-10-18", "lines": [{"purchase_order_line_id": str(line.id), "quantity_received": "8"}]}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert received.status_code == 201, received.data
    grn = GRN.objects.get(id=received.data["id"])
    assert grn.quality_status == "PENDING" and grn.lines.get().quantity_received == Decimal("8")
    quality = client.patch("/api/v1/grns", {"grn_id": str(grn.id), "quality_status": "PARTIAL", "quality_note": "Two units not received"}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert quality.status_code == 200 and quality.data["quality_status"] == "PARTIAL"
    second = client.post("/api/v1/grns", {"purchase_order_id": str(po.id), "number": "GRN-P3-2", "received_at": "2026-10-18", "lines": [{"purchase_order_line_id": str(line.id), "quantity_received": "2"}]}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert second.status_code == 201
    over_receipt = client.post("/api/v1/grns", {"purchase_order_id": str(po.id), "number": "GRN-P3-3", "received_at": "2026-10-18", "lines": [{"purchase_order_line_id": str(line.id), "quantity_received": "0.000001"}]}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert over_receipt.status_code == 409 and over_receipt.data["error"]["code"] == "RECEIPT_LIMIT_EXCEEDED"
    control = client.patch("/api/v1/matching/settings", {"over_receipt_tolerance_percent": "10"}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert control.status_code == 200
    within_tolerance = client.post("/api/v1/grns", {"purchase_order_id": str(po.id), "number": "GRN-P3-4", "received_at": "2026-10-18", "lines": [{"purchase_order_line_id": str(line.id), "quantity_received": "1"}]}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert within_tolerance.status_code == 201
    outside_tolerance = client.post("/api/v1/grns", {"purchase_order_id": str(po.id), "number": "GRN-P3-5", "received_at": "2026-10-18", "lines": [{"purchase_order_line_id": str(line.id), "quantity_received": "0.000001"}]}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert outside_tolerance.status_code == 409


@pytest.mark.django_db
def test_purchase_order_draft_edits_are_versioned_and_tenant_scoped(finance_client):
    tenant, user, client = finance_client
    vendor = Vendor.objects.create(tenant=tenant, name="Original vendor")
    replacement_vendor = Vendor.objects.create(tenant=tenant, name="Replacement vendor")
    outsider = Tenant.objects.create(name="Different PO tenant", workspace_key="different-po-tenant")
    outsider_vendor = Vendor.objects.create(tenant=outsider, name="Outsider vendor")
    base = {"vendor_id": str(vendor.id), "number": "PO-VERSIONS-1", "order_date": "2026-10-18", "lines": [
        {"description": "Steel sheet", "item_code": "ST-1", "quantity": "5", "uom": "EA", "rate": "12.50", "gst_rate": "18"},
        {"description": "Cutting service", "quantity": "2", "uom": "HOUR", "rate": "20", "gst_rate": "18"},
    ]}
    created = client.post("/api/v1/purchase-orders", base, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert created.status_code == 201
    po = PurchaseOrder.objects.get(id=created.data["id"])
    from procurement.models import PurchaseOrderRevision
    assert po.revision == 1 and PurchaseOrderRevision.objects.filter(purchase_order=po, revision=1).exists()
    updated = {"purchase_order_id": str(po.id), "action": "edit", "vendor_id": str(replacement_vendor.id), "order_date": "2026-10-19", "change_note": "Supplier quotation and delivery scope updated.", "lines": [
        {"description": "Steel sheet revised", "item_code": "ST-1", "quantity": "6", "uom": "EA", "rate": "13", "gst_rate": "18"},
        {"description": "Cutting service", "quantity": "3", "uom": "HOUR", "rate": "20", "gst_rate": "18"},
    ]}
    edited = client.patch("/api/v1/purchase-orders", updated, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert edited.status_code == 200 and edited.data["revision"] == 2
    history = client.get(f"/api/v1/purchase-orders/{po.id}/revisions", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert history.status_code == 200 and [row["revision"] for row in history.data] == [2, 1]
    assert history.data[1]["snapshot"]["vendor_name"] == "Original vendor"
    assert history.data[0]["snapshot"]["vendor_name"] == "Replacement vendor"
    assert len(history.data[0]["snapshot"]["lines"]) == 2
    cross_tenant_vendor = {**updated, "vendor_id": str(outsider_vendor.id), "change_note": "This change must not cross tenants."}
    denied = client.patch("/api/v1/purchase-orders", cross_tenant_vendor, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert denied.status_code == 404
    submitted = client.patch("/api/v1/purchase-orders", {"purchase_order_id": str(po.id), "action": "submit"}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert submitted.status_code == 200
    locked = client.patch("/api/v1/purchase-orders", updated, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert locked.status_code == 409
    po.refresh_from_db()
    assert po.revision == 2 and po.vendor_id == replacement_vendor.id


@pytest.mark.django_db
def test_purchase_order_csv_import_creates_revision_history(finance_client):
    tenant, _, client = finance_client
    vendor = Vendor.objects.create(tenant=tenant, name="CSV PO supplier", external_code="CSV-SUP-1")
    first = SimpleUploadedFile("purchase-orders.csv", b"po_number,vendor_code,order_date,line_no,item_code,description,quantity,uom,rate,gst_rate\nPO-CSV-V1,CSV-SUP-1,2026-10-18,1,ITEM-1,Imported part,4,EA,12.50,18\n", content_type="text/csv")
    created = client.post("/api/v1/purchase-orders/import", {"file": first}, format="multipart", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert created.status_code == 200 and created.data["accepted_rows"] == 1
    po = PurchaseOrder.objects.get(tenant=tenant, number="PO-CSV-V1")
    second = SimpleUploadedFile("purchase-orders.csv", b"po_number,vendor_code,order_date,line_no,item_code,description,quantity,uom,rate,gst_rate\nPO-CSV-V1,CSV-SUP-1,2026-10-18,1,ITEM-1,Revised imported part,6,EA,13.00,18\n", content_type="text/csv")
    updated = client.post("/api/v1/purchase-orders/import", {"file": second}, format="multipart", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert updated.status_code == 200 and updated.data["accepted_rows"] == 1
    history = client.get(f"/api/v1/purchase-orders/{po.id}/revisions", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert [item["revision"] for item in history.data] == [2, 1]
    assert history.data[1]["snapshot"]["lines"][0]["description"] == "Imported part"
    assert history.data[0]["snapshot"]["lines"][0]["description"] == "Revised imported part"


@pytest.mark.django_db
def test_grn_csv_import_cannot_exceed_cumulative_po_line_balance(finance_client):
    tenant, _, client = finance_client
    vendor = Vendor.objects.create(tenant=tenant, name="Imported receipt supplier", approved=True)
    po = PurchaseOrder.objects.create(tenant=tenant, vendor=vendor, number="PO-IMPORT-BALANCE", status=PurchaseOrder.Status.APPROVED)
    line = PurchaseOrderLine.objects.create(tenant=tenant, purchase_order=po, line_no=1, description="Imported part", quantity="10", rate="2")
    first = SimpleUploadedFile("first.csv", b"po_number,grn_number,po_line_no,quantity_received\nPO-IMPORT-BALANCE,GRN-IMPORT-1,1,8\n", content_type="text/csv")
    accepted = client.post("/api/v1/grns/import", {"file": first}, format="multipart", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert accepted.status_code == 200 and accepted.data["accepted_rows"] == 1
    second = SimpleUploadedFile("second.csv", b"po_number,grn_number,po_line_no,quantity_received\nPO-IMPORT-BALANCE,GRN-IMPORT-2,1,3\n", content_type="text/csv")
    rejected = client.post("/api/v1/grns/import", {"file": second}, format="multipart", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert rejected.status_code == 207 and rejected.data["accepted_rows"] == 0
    assert "remaining receivable quantity of 2" in rejected.data["errors"][0]["message"]
    assert GRNLine.objects.filter(tenant=tenant, purchase_order_line=line).count() == 1


@pytest.mark.django_db
def test_vendor_portal_invite_upload_and_supplier_question_are_vendor_scoped(finance_client):
    import hashlib
    from documents.models import Document
    from invoices.models import Invoice
    tenant, user, client = finance_client
    vendor = Vendor.objects.create(tenant=tenant, name="Portal supplier", gstin="27ABCDE1234F1Z5", approved=True)
    other_vendor = Vendor.objects.create(tenant=tenant, name="Other supplier", approved=True)
    created = client.post("/api/v1/vendor-portal/invitations", {"vendor_id": str(vendor.id), "expires_in_days": 5}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert created.status_code == 201
    token = created.data["token"]
    invite = VendorPortalInvite.objects.get(id=created.data["id"])
    assert invite.token_hash == hashlib.sha256(token.encode()).hexdigest()
    public = APIClient()
    png = b"\x89PNG\r\n\x1a\n" + b"invoice-data"
    upload = SimpleUploadedFile("invoice.png", png, content_type="image/png")
    submitted = public.post(f"/api/v1/vendor-portal/access/{token}", {"file": upload, "invoice_number": "VEND-100", "invoice_date": "2026-10-18", "invoice_total": "420.50"}, format="multipart")
    assert submitted.status_code == 201, submitted.data
    invoice = Invoice.objects.get(id=submitted.data["invoice_id"])
    assert invoice.vendor_id == vendor.id and invoice.source_channel == "VENDOR_PORTAL" and invoice.uploaded_by_id is None
    question = public.post(f"/api/v1/vendor-portal/access/{token}", {"action": "message", "invoice_id": str(invoice.id), "body": "Can you confirm receipt?"}, format="json")
    assert question.status_code == 201
    private = Invoice.objects.create(tenant=tenant, vendor=other_vendor, invoice_number="OTHER-1")
    cross_vendor_message = public.post(f"/api/v1/vendor-portal/access/{token}", {"action": "message", "invoice_id": str(private.id), "body": "Not mine"}, format="json")
    assert cross_vendor_message.status_code == 400
    assert Document.objects.filter(tenant=tenant).count() == 1
    assert VendorPortalInvite.objects.get(id=invite.id).created_by_id == user.id


@pytest.mark.django_db
def test_vendor_portal_rejects_expired_or_revoked_tokens(finance_client):
    import hashlib
    tenant, _, _ = finance_client
    vendor = Vendor.objects.create(tenant=tenant, name="Expired portal vendor")
    invite = VendorPortalInvite.objects.create(tenant=tenant, vendor=vendor, token_hash=hashlib.sha256(b"expired-token").hexdigest(), expires_at=timezone.now() - timedelta(minutes=1))
    client = APIClient()
    expired = client.get("/api/v1/vendor-portal/access/expired-token")
    assert expired.status_code == 404


@pytest.mark.django_db
def test_workspace_directory_only_lists_active_user_memberships(finance_client):
    tenant, user, client = finance_client
    second = Tenant.objects.create(name="Second Company", workspace_key="second-company-p3")
    Membership.objects.create(tenant=second, user=user, role="AUDITOR")
    inactive = Tenant.objects.create(name="Inactive Company", workspace_key="inactive-company-p3")
    Membership.objects.create(tenant=inactive, user=user, role="FINANCE", is_active=False)
    response = client.get("/api/v1/auth/workspaces", HTTP_X_WORKSPACE="nonexistent")
    assert response.status_code == 200
    assert {row["workspace_key"] for row in response.data} == {tenant.workspace_key, second.workspace_key}


@pytest.mark.django_db
def test_ai_review_requires_workspace_enablement_and_human_review(monkeypatch, finance_client):
    from invoices.models import Invoice
    from audit.models import AuditLog
    tenant, _, client = finance_client
    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-openai-key")
    invoice = Invoice.objects.create(tenant=tenant, invoice_number="AI-1", invoice_total="250", status=Invoice.Status.APPROVAL_PENDING)
    path = "/api/v1/ai-review/suggestions"
    off = client.post(path, {"invoice_id": str(invoice.id), "confirm_external_processing": True}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert off.status_code == 409
    tenant.settings = {"ai_review_enabled": True, "ai_review_provider": "openai"}; tenant.save(update_fields=["settings"])
    monkeypatch.setattr("phase3.views._openai_invoice_review", lambda model, data: [{"kind": "DOCUMENT_GAP", "title": "Check invoice reference", "rationale": "The reference field is empty.", "confidence": 0.78, "evidence_fields": ["invoice_number"]}])
    unconfirmed = client.post(path, {"invoice_id": str(invoice.id), "confirm_external_processing": False}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert unconfirmed.status_code == 400
    result = client.post(path, {"invoice_id": str(invoice.id), "confirm_external_processing": True}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert result.status_code == 201 and len(result.data["suggestions"]) == 1
    suggestion = AIReviewSuggestion.objects.get(tenant=tenant)
    reviewed = client.patch(path, {"suggestion_id": str(suggestion.id), "decision": "ACCEPTED"}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert reviewed.status_code == 200 and reviewed.data["status"] == "ACCEPTED"
    invoice.refresh_from_db()
    assert invoice.status == Invoice.Status.APPROVAL_PENDING
    assert AuditLog.objects.filter(tenant=tenant, action="AI_SUGGESTION_ACCEPTED").count() == 1


@pytest.mark.django_db
def test_ai_review_workspace_enablement_is_owner_only(monkeypatch, finance_client):
    tenant, user, client = finance_client
    response = client.patch("/api/v1/ai-review/settings", {"enabled": True}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert response.status_code == 403
    user.memberships.filter(tenant=tenant).update(role="OWNER")
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    enabled = client.patch("/api/v1/ai-review/settings", {"enabled": True}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert enabled.status_code == 200 and enabled.data["enabled"] is True


def test_gemini_ai_review_uses_structured_output_and_api_key_header(monkeypatch):
    import json
    from phase3 import views
    monkeypatch.setenv("GEMINI_API_KEY", "unit-test-gemini-key")
    captured = {}
    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def read(self, _limit):
            return json.dumps({"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": '{"suggestions": []}'}]}}]}).encode()
    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = request.headers
        captured["payload"] = json.loads(request.data)
        captured["timeout"] = timeout
        return FakeResponse()
    monkeypatch.setattr(views.urllib.request, "urlopen", fake_urlopen)
    assert views._gemini_invoice_review("gemini-test-model", {"invoice_number": "G-1"}) == []
    assert captured["url"].endswith("/models/gemini-test-model:generateContent")
    assert captured["headers"]["X-goog-api-key"] == "unit-test-gemini-key"
    assert captured["payload"]["generationConfig"]["responseMimeType"] == "application/json"
    assert captured["payload"]["generationConfig"]["responseSchema"] == views.AI_REVIEW_SCHEMA
    assert captured["timeout"] == 30


@pytest.mark.django_db
def test_ai_review_provider_is_owner_configurable_and_requires_selected_key(monkeypatch, finance_client):
    tenant, user, client = finance_client
    user.memberships.filter(tenant=tenant).update(role="OWNER")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    unavailable = client.patch("/api/v1/ai-review/settings", {"provider": "gemini", "enabled": True}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert unavailable.status_code == 409 and "GEMINI_API_KEY" in unavailable.data["error"]
    monkeypatch.setenv("GEMINI_API_KEY", "unit-test-gemini-key")
    selected = client.patch("/api/v1/ai-review/settings", {"provider": "gemini", "enabled": True}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert selected.status_code == 200 and selected.data == {"enabled": True, "provider": "gemini"}
    status = client.get("/api/v1/ai-review/settings", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert status.data["provider_configured"] is True and status.data["model"]
    assert status.data["providers"]["gemini"]["configured"] is True


@pytest.mark.django_db
def test_api_key_is_hashed_tenant_scoped_and_revocable(finance_client):
    tenant, user, client = finance_client
    user.memberships.filter(tenant=tenant).update(role="OWNER")
    created = client.post("/api/v1/api-keys", {"name": "Reporting sync", "scopes": ["invoices:read"]}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert created.status_code == 201
    key = TenantAPIKey.objects.get(id=created.data["id"])
    assert key.secret_hash != created.data["token"] and key.prefix in created.data["token"]
    Invoice.objects.create(tenant=tenant, invoice_number="EXTERNAL-1", invoice_total="50")
    external = APIClient().get("/api/v1/external/invoices", HTTP_AUTHORIZATION=f"Bearer {created.data['token']}")
    assert external.status_code == 200 and len(external.data["results"]) == 1
    client.patch(f"/api/v1/api-keys/{key.id}", {}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    denied = APIClient().get("/api/v1/external/invoices", HTTP_AUTHORIZATION=f"Bearer {created.data['token']}")
    assert denied.status_code == 401


@pytest.mark.django_db
def test_existing_api_keys_and_vendor_links_follow_workspace_lifecycle_and_branch_scope(finance_client):
    import hashlib
    tenant, user, client = finance_client
    Membership.objects.filter(tenant=tenant, user=user).update(role="OWNER")
    key_response = client.post("/api/v1/api-keys", {"name": "Lifecycle report", "scopes": ["invoices:read"]},
        format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert key_response.status_code == 201
    key = TenantAPIKey.objects.get(id=key_response.data["id"])
    invoice = Invoice.objects.create(tenant=tenant, invoice_number="LIFECYCLE-1", invoice_total="15")
    plan = Plan.objects.create(name="Lifecycle plan", slug="lifecycle-plan")
    api_feature, _ = Feature.objects.get_or_create(key="api_access", defaults={"name": "Public API"})
    PlanFeature.objects.create(plan=plan, feature=api_feature, enabled=True)
    subscription = Subscription.objects.create(tenant=tenant, plan=plan, status=Subscription.Status.ACTIVE)
    vendor = Vendor.objects.create(tenant=tenant, name="Lifecycle supplier")
    token = "lifecycle-vendor-token"
    VendorPortalInvite.objects.create(tenant=tenant, vendor=vendor,
        token_hash=hashlib.sha256(token.encode()).hexdigest(), expires_at=timezone.now()+timedelta(days=1))
    external = APIClient()
    headers = {"HTTP_AUTHORIZATION": f"Bearer {key_response.data['token']}"}
    assert external.get("/api/v1/external/invoices", **headers).status_code == 200
    public = APIClient()
    path = f"/api/v1/vendor-portal/access/{token}"
    assert public.get(path).status_code == 200

    subscription.status = Subscription.Status.SUSPENDED
    subscription.save(update_fields=["status"])
    assert external.get("/api/v1/external/invoices", **headers).status_code == 403
    assert public.get(path).status_code == 404
    assert public.post(path, {"action": "message", "invoice_id": str(invoice.id), "body": "Suspended update"}, format="json").status_code == 404
    tenant.invoice_intake_token = "intake-lifecycle-token"
    tenant.save(update_fields=["invoice_intake_token"])
    intake = public.post(f"/api/v1/email-ingestion/{tenant.workspace_key}", {"message_id": "paused-message"},
        format="json", HTTP_X_INVOICE_INTAKE_TOKEN=tenant.invoice_intake_token)
    assert intake.status_code == 403
    membership = Membership.objects.get(tenant=tenant, user=user)
    membership.branch_scope_enabled = True
    membership.save(update_fields=["branch_scope_enabled"])
    subscription.status = Subscription.Status.ACTIVE
    subscription.save(update_fields=["status"])
    assert external.get("/api/v1/external/invoices", **headers).status_code == 403

    membership.branch_scope_enabled = False
    membership.save(update_fields=["branch_scope_enabled"])
    tenant.is_deleted = True
    tenant.save(update_fields=["is_deleted"])
    assert external.get("/api/v1/external/invoices", **headers).status_code == 403
    assert public.get(path).status_code == 404
    assert client.get("/api/v1/auth/me", HTTP_X_WORKSPACE=tenant.workspace_key).status_code == 403


@pytest.mark.django_db
def test_webhook_secret_is_encrypted_and_invoice_event_is_queued(monkeypatch, finance_client):
    from cryptography.fernet import Fernet
    from phase3 import services
    from django.conf import settings
    tenant, user, client = finance_client
    user.memberships.filter(tenant=tenant).update(role="OWNER")
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "WEBHOOK_FERNET_KEY", key)
    monkeypatch.setattr("phase3.views.validate_public_webhook_url", lambda url: (None, "203.0.113.3"))
    created = client.post("/api/v1/webhooks", {"name": "ERP events", "url": "https://hooks.example.com/kriyopay", "events": ["invoice.created"]}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert created.status_code == 201, created.data
    endpoint = WebhookEndpoint.objects.get(id=created.data["id"])
    assert created.data["secret"] not in endpoint.encrypted_secret
    assert services.decrypt_signing_secret(endpoint) == created.data["secret"]
    Invoice.objects.create(tenant=tenant, invoice_number="HOOK-1", invoice_total="25.00")
    assert services.queue_webhook_event(tenant, "invoice.created", {"invoice_number": "HOOK-1"}) == 1
    delivery = WebhookDelivery.objects.get(endpoint=endpoint, event_type="invoice.created")
    assert delivery.payload["data"]["invoice_number"] == "HOOK-1" and delivery.status == "QUEUED"
    listed = client.get(f"/api/v1/webhooks/{endpoint.id}", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert listed.status_code == 200 and "secret" not in listed.data


@pytest.mark.django_db
def test_webhook_test_event_only_queues_for_subscribed_endpoint(monkeypatch, finance_client):
    from cryptography.fernet import Fernet
    from django.conf import settings
    from phase3.services import encrypt_signing_secret
    tenant, user, client = finance_client
    user.memberships.filter(tenant=tenant).update(role="OWNER")
    monkeypatch.setattr(settings, "WEBHOOK_FERNET_KEY", Fernet.generate_key().decode())
    endpoint = WebhookEndpoint.objects.create(tenant=tenant, name="No test event", url="https://example.com/hook", encrypted_secret=encrypt_signing_secret("secret"), events=["invoice.created"], created_by=user)
    response = client.post(f"/api/v1/webhooks/{endpoint.id}/test", {}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert response.status_code == 409
    assert endpoint.deliveries.count() == 0


@pytest.mark.django_db
def test_webhook_delivery_signs_payload_and_records_receiver_status(monkeypatch, finance_client):
    from cryptography.fernet import Fernet
    from django.conf import settings
    from phase3 import services
    tenant, user, client = finance_client
    monkeypatch.setattr(settings, "WEBHOOK_FERNET_KEY", Fernet.generate_key().decode())
    endpoint = WebhookEndpoint.objects.create(tenant=tenant, name="Receiver", url="https://hooks.example.com/x", encrypted_secret=services.encrypt_signing_secret("shared-secret"), events=["invoice.created"], created_by=user)
    delivery = WebhookDelivery.objects.create(tenant=tenant, endpoint=endpoint, event_type="invoice.created", payload={"id": "evt-1", "type": "invoice.created", "data": {"invoice_id": "inv-1"}})
    captured = {}
    class FakeResponse:
        status = 204
        def read(self, _limit): return b""
    class FakeConnection:
        def __init__(self, host, address): captured["host"] = host; captured["address"] = address
        def request(self, method, path, body, headers):
            captured.update(method=method, path=path, body=body, headers=headers)
            assert services.deliver_one(delivery) == WebhookDelivery.Status.DELIVERING
            assert "request_count" not in captured
            captured["request_count"] = 1
        def getresponse(self): return FakeResponse()
        def close(self): pass
    monkeypatch.setattr(services, "validate_public_webhook_url", lambda url: (__import__("urllib.parse", fromlist=["urlsplit"]).urlsplit(url), "8.8.8.8"))
    monkeypatch.setattr(services, "PinnedHTTPSConnection", FakeConnection)
    assert services.deliver_one(delivery) == WebhookDelivery.Status.DELIVERED
    assert captured["request_count"] == 1
    delivery.refresh_from_db()
    import hmac
    import hashlib
    expected = "sha256=" + hmac.new(b"shared-secret", captured["body"], hashlib.sha256).hexdigest()
    assert captured["headers"]["X-KriyoPay-Signature-256"] == expected
    assert delivery.attempts == 1 and delivery.response_code == 204 and delivery.delivered_at is not None


@pytest.mark.django_db
def test_deliver_webhooks_command_dry_run_counts_without_sending(finance_client, monkeypatch):
    from io import StringIO
    from django.core.management import call_command
    from phase3.management.commands import deliver_webhooks

    tenant, user, _client = finance_client
    endpoint = WebhookEndpoint.objects.create(tenant=tenant, name="Dry run", url="https://hooks.example.com/x",
        encrypted_secret="encrypted-placeholder", events=["invoice.created"], created_by=user)
    delivery = WebhookDelivery.objects.create(tenant=tenant, endpoint=endpoint, event_type="invoice.created", payload={"id": "evt-dry-run"})
    monkeypatch.setattr(deliver_webhooks, "deliver_due_webhooks", lambda **kwargs: (_ for _ in ()).throw(AssertionError("dry run attempted delivery")))
    output = StringIO()
    call_command("deliver_webhooks", "--dry-run", "--limit", "10", stdout=output)
    delivery.refresh_from_db()
    assert "1 webhook delivery attempt" in output.getvalue()
    assert delivery.status == WebhookDelivery.Status.QUEUED and delivery.attempts == 0


@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(connection.vendor != "postgresql", reason="Requires PostgreSQL row locks")
def test_concurrent_webhook_workers_claim_delivery_once(monkeypatch, finance_client):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event, Lock
    from cryptography.fernet import Fernet
    from django.conf import settings
    from django.db import close_old_connections, connections
    from phase3 import services

    tenant, user, _client = finance_client
    monkeypatch.setattr(settings, "WEBHOOK_FERNET_KEY", Fernet.generate_key().decode())
    endpoint = WebhookEndpoint.objects.create(tenant=tenant, name="Concurrent receiver", url="https://hooks.example.com/x",
        encrypted_secret=services.encrypt_signing_secret("shared-secret"), events=["invoice.created"], created_by=user)
    delivery = WebhookDelivery.objects.create(tenant=tenant, endpoint=endpoint, event_type="invoice.created", payload={"id": "evt-concurrent"})
    started, release = Event(), Event()
    request_count = [0]
    request_lock = Lock()

    class FakeResponse:
        status = 204
        def read(self, _limit): return b""

    class FakeConnection:
        def __init__(self, host, address): pass
        def request(self, method, path, body, headers):
            with request_lock:
                request_count[0] += 1
            started.set()
            assert release.wait(timeout=10)
        def getresponse(self): return FakeResponse()
        def close(self): pass

    monkeypatch.setattr(services, "validate_public_webhook_url", lambda url: (__import__("urllib.parse", fromlist=["urlsplit"]).urlsplit(url), "8.8.8.8"))
    monkeypatch.setattr(services, "PinnedHTTPSConnection", FakeConnection)
    def send():
        close_old_connections()
        try:
            return services.deliver_one(delivery)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as workers:
        first = workers.submit(send)
        assert started.wait(timeout=10)
        second = workers.submit(send)
        assert second.result(timeout=10) == WebhookDelivery.Status.DELIVERING
        release.set()
        assert first.result(timeout=10) == WebhookDelivery.Status.DELIVERED
    assert request_count[0] == 1


@pytest.mark.django_db
def test_failed_webhook_delivery_history_and_bounded_manual_retry(monkeypatch, finance_client):
    from cryptography.fernet import Fernet
    from django.conf import settings
    from audit.models import AuditLog
    tenant, user, client = finance_client
    user.memberships.filter(tenant=tenant).update(role="OWNER")
    from phase3.services import encrypt_signing_secret
    monkeypatch.setattr(settings, "WEBHOOK_FERNET_KEY", Fernet.generate_key().decode())
    endpoint = WebhookEndpoint.objects.create(tenant=tenant, name="Retry endpoint", url="https://hooks.example.test/erp", encrypted_secret=encrypt_signing_secret("retry-secret"), events=["invoice.created"], created_by=user)
    delivery = WebhookDelivery.objects.create(tenant=tenant, endpoint=endpoint, event_type="invoice.created",
        payload={"id": "stable-event-id", "type": "invoice.created", "data": {"invoice_number": "RETRY-1"}},
        status=WebhookDelivery.Status.FAILED, attempts=6, cycle_attempts=6, error="Receiver returned HTTP 503", response_code=503)
    detail = client.get(f"/api/v1/webhooks/{endpoint.id}", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert detail.status_code == 200 and detail.data["deliveries"][0]["retry_available"] is True
    retried = client.post(f"/api/v1/webhooks/deliveries/{delivery.id}/retry", {}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert retried.status_code == 202
    delivery.refresh_from_db()
    assert delivery.status == WebhookDelivery.Status.QUEUED and delivery.cycle_attempts == 0
    assert delivery.attempts == 6 and delivery.manual_retry_count == 1 and delivery.payload["id"] == "stable-event-id"
    assert AuditLog.objects.filter(tenant=tenant, action="WEBHOOK_DELIVERY_MANUALLY_REQUEUED", object_id=str(delivery.id)).exists()
    delivery.status = WebhookDelivery.Status.FAILED; delivery.manual_retry_count = 3; delivery.save(update_fields=["status", "manual_retry_count"])
    exhausted = client.post(f"/api/v1/webhooks/deliveries/{delivery.id}/retry", {}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert exhausted.status_code == 409


@pytest.mark.django_db
def test_invalid_webhook_encryption_key_returns_configuration_error(monkeypatch, finance_client):
    from django.conf import settings
    tenant, user, client = finance_client
    user.memberships.filter(tenant=tenant).update(role="OWNER")
    monkeypatch.setattr(settings, "WEBHOOK_FERNET_KEY", "bad-key")
    monkeypatch.setattr("phase3.views.validate_public_webhook_url", lambda url: (None, "8.8.8.8"))
    response = client.post("/api/v1/webhooks", {"name": "Broken crypto", "url": "https://hooks.example.com/event", "events": ["invoice.created"]}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert response.status_code == 409
    assert "WEBHOOK_FERNET_KEY is invalid" in response.data["error"]


@pytest.mark.django_db
def test_bank_xlsx_import_maps_headers_and_preserves_excel_dates(finance_client):
    from io import BytesIO
    from datetime import date
    from openpyxl import Workbook
    tenant, _, client = finance_client
    workbook = Workbook(); sheet = workbook.active
    sheet.append(["Booking date", "Narrative", "Bank reference", "Debit/Credit"])
    sheet.append([date(2026, 10, 18), "Supplier remittance", "UTR-XLS-1", -250.75])
    data = BytesIO(); workbook.save(data)
    upload = SimpleUploadedFile("bank.xlsx", data.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response = client.post("/api/v1/bank-reconciliation", {"file": upload, "date_column": "Booking date", "description_column": "Narrative", "reference_column": "Bank reference", "amount_column": "Debit/Credit"}, format="multipart", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert response.status_code == 201, response.data
    txn = BankTransaction.objects.get(tenant=tenant)
    assert txn.transaction_date == date(2026, 10, 18)
    assert txn.reference == "UTR-XLS-1" and txn.amount == Decimal("-250.75")


@pytest.mark.django_db
def test_tax_review_flags_line_arithmetic_and_month_end_review_is_audited(finance_client):
    from audit.models import AuditLog
    from datetime import date
    tenant, user, client = finance_client
    invoice = Invoice.objects.create(
        tenant=tenant, invoice_number="TAX-LINE-1", invoice_date=date(2026, 10, 10),
        supplier_gstin="27ABCDE1234F1Z5", taxable_total="100", gst_total="18",
        tds_total="0", invoice_total="118",
    )
    InvoiceLine.objects.create(
        tenant=tenant, invoice=invoice, line_no=1, description="Service", hsn_sac="9983",
        taxable_value="100", gst_rate="18", gst_amount="17", tds_amount="0",
    )
    tax = client.get("/api/v1/compliance/tax-reviews", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert tax.status_code == 200
    assert "GST arithmetic needs review on line 1" in tax.data["results"][0]["issues"]
    month_end = client.get("/api/v1/compliance/month-end?period=2026-10", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert month_end.status_code == 200
    assert "not a statutory filing" in month_end.data["note"]
    arithmetic = next(row for row in month_end.data["items"] if row["key"] == "tax_arithmetic")
    assert arithmetic["outstanding_count"] == 1 and arithmetic["status"] == "OPEN"
    saved = client.post(
        "/api/v1/compliance/month-end",
        {"period": "2026-10", "item_key": "tax_arithmetic", "review_note": "Checked line totals against the source invoice."},
        format="json", HTTP_X_WORKSPACE=tenant.workspace_key,
    )
    assert saved.status_code == 200 and saved.data["status"] == "REVIEWED"
    refreshed = client.get("/api/v1/compliance/month-end?period=2026-10", HTTP_X_WORKSPACE=tenant.workspace_key)
    reviewed = next(row for row in refreshed.data["items"] if row["key"] == "tax_arithmetic")
    assert reviewed["status"] == "REVIEWED" and reviewed["reviewed_by"] == user.get_full_name()
    assert AuditLog.objects.filter(tenant=tenant, action="MONTH_END_ITEM_REVIEWED").count() == 1


@pytest.mark.django_db
def test_month_end_review_requires_finance_role(finance_client):
    tenant, user, client = finance_client
    user.memberships.filter(tenant=tenant).update(role="AUDITOR")
    response = client.post(
        "/api/v1/compliance/month-end",
        {"period": "2026-10", "item_key": "tax_review", "review_note": "Checked the open invoices."},
        format="json", HTTP_X_WORKSPACE=tenant.workspace_key,
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_gmail_oauth_uses_read_only_scope_and_encrypted_refresh_token(monkeypatch, finance_client):
    from urllib.parse import parse_qs, urlparse
    from django.conf import settings
    from cryptography.fernet import Fernet
    from audit.models import AuditLog
    tenant, _, client = finance_client
    monkeypatch.setattr(settings, "WEBHOOK_FERNET_KEY", Fernet.generate_key().decode())
    started = client.post("/api/v1/google/gmail", {}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert started.status_code == 200, started.data
    query = parse_qs(urlparse(started.data["authorization_url"]).query)
    assert query["redirect_uri"][0] == "http://localhost:3000/integrations/gmail/callback"
    assert "https://www.googleapis.com/auth/gmail.readonly" in query["scope"][0].split()
    assert query["access_type"] == ["offline"] and query["prompt"] == ["consent"]
    state = query["state"][0]
    monkeypatch.setattr("phase3.views.exchange_gmail_code", lambda code: {"access_token": "test-access", "refresh_token": "test-refresh", "scope": "openid email profile https://www.googleapis.com/auth/gmail.readonly"})
    monkeypatch.setattr("phase3.views.get_google_profile", lambda token: {"subject": "google-subject-1", "email": "finance@example.test"})
    callback = APIClient().post("/api/v1/google/gmail/oauth/callback", {"state": state, "code": "one-time-code"}, format="json")
    assert callback.status_code == 200 and callback.data["connected"] is True
    connection = GmailConnection.objects.get(tenant=tenant)
    assert connection.email == "finance@example.test" and connection.active
    assert connection.encrypted_refresh_token != "test-refresh"
    status = client.get("/api/v1/google/gmail", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert status.status_code == 200 and status.data["email"] == "finance@example.test"
    from phase3.services import _fernet
    assert _fernet().decrypt(connection.encrypted_refresh_token.encode()).decode() == "test-refresh"
    replay = APIClient().post("/api/v1/google/gmail/oauth/callback", {"state": state, "code": "one-time-code"}, format="json")
    assert replay.status_code == 400
    disconnected = client.delete("/api/v1/google/gmail", {}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    connection.refresh_from_db()
    assert disconnected.status_code == 200 and connection.active is False and connection.encrypted_refresh_token == ""
    assert AuditLog.objects.filter(tenant=tenant, action="GMAIL_ACCOUNT_DISCONNECTED").count() == 1


@pytest.mark.django_db
def test_gmail_sync_imports_supported_attachment_once_without_mailbox_mutations(monkeypatch, finance_client):
    import base64
    from django.conf import settings
    from cryptography.fernet import Fernet
    from phase3.services import encrypt_signing_secret
    from inbound_email.models import EmailIngestionLog
    from documents.models import Document
    tenant, user, client = finance_client
    monkeypatch.setattr(settings, "WEBHOOK_FERNET_KEY", Fernet.generate_key().decode())
    connection = GmailConnection.objects.create(tenant=tenant, google_subject="g-sub", email="ap@example.test",
        encrypted_refresh_token=encrypt_signing_secret("refresh"), scopes=["https://www.googleapis.com/auth/gmail.readonly"], connected_by=user)
    monkeypatch.setattr("phase3.views.refresh_gmail_access_token", lambda token: "access")
    pdf = b"%PDF-1.7 sample invoice"
    payload = {"mimeType": "multipart/mixed", "parts": [{"filename": "invoice.pdf", "mimeType": "application/pdf",
        "body": {"data": base64.urlsafe_b64encode(pdf).decode().rstrip("=")}}], "headers": [
        {"name": "From", "value": "Vendor <vendor@example.test>"}, {"name": "Subject", "value": "Invoice 42"}]}
    requested_paths = []
    def gmail_api(token, path, params=None):
        requested_paths.append((path, params))
        if path == "messages": return {"messages": [{"id": "gmail-message-42"}]}
        return {"id": "gmail-message-42", "internalDate": "1792260000000", "payload": payload}
    monkeypatch.setattr("phase3.views.gmail_api", gmail_api)
    first = client.post("/api/v1/google/gmail/sync", {}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert first.status_code == 200, first.data
    assert first.data["attachments_imported"] == 1, {"response": first.data, "provider_calls": requested_paths}
    assert first.data["messages_checked"] == 1
    log = EmailIngestionLog.objects.get(tenant=tenant, provider="GMAIL", message_id="gmail-message-42")
    assert log.status == EmailIngestionLog.Status.PROCESSED
    assert log.claimed_at is None and log.processing_token is None
    assert Document.objects.filter(tenant=tenant).count() == 1
    assert not any(path.endswith("/modify") or path.endswith("/trash") for path, _ in requested_paths)
    second = client.post("/api/v1/google/gmail/sync", {}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert second.status_code == 200 and second.data["messages_skipped"] == 1
    assert Document.objects.filter(tenant=tenant).count() == 1


@pytest.mark.django_db
def test_gmail_sync_skips_a_message_with_a_live_processing_lease(monkeypatch, finance_client):
    import uuid
    from django.conf import settings
    from cryptography.fernet import Fernet
    from phase3.services import encrypt_signing_secret
    from inbound_email.models import EmailIngestionLog

    tenant, user, client = finance_client
    monkeypatch.setattr(settings, "WEBHOOK_FERNET_KEY", Fernet.generate_key().decode())
    GmailConnection.objects.create(tenant=tenant, google_subject="g-live", email="ap-live@example.test",
        encrypted_refresh_token=encrypt_signing_secret("refresh"), scopes=["https://www.googleapis.com/auth/gmail.readonly"], connected_by=user)
    lease = uuid.uuid4()
    log = EmailIngestionLog.objects.create(tenant=tenant, provider="GMAIL", message_id="gmail-live-lease",
        status=EmailIngestionLog.Status.PROCESSING, claimed_at=timezone.now(), processing_token=lease)
    monkeypatch.setattr("phase3.views.refresh_gmail_access_token", lambda token: "access")
    details_requested = []
    def gmail_api(_token, path, params=None):
        if path == "messages": return {"messages": [{"id": "gmail-live-lease"}]}
        details_requested.append(path)
        return {"id": "gmail-live-lease", "payload": {"headers": [], "parts": []}}
    monkeypatch.setattr("phase3.views.gmail_api", gmail_api)

    response = client.post("/api/v1/google/gmail/sync", {}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert response.status_code == 200, response.data
    assert response.data["messages_skipped"] == 1
    assert response.data["results"][0]["status"] == "ALREADY_PROCESSING"
    assert details_requested == []
    log.refresh_from_db()
    assert log.processing_token == lease and log.status == EmailIngestionLog.Status.PROCESSING

    log.claimed_at = timezone.now() - timedelta(minutes=20)
    log.save(update_fields=["claimed_at"])
    recovered = client.post("/api/v1/google/gmail/sync", {}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert recovered.status_code == 200, recovered.data
    assert details_requested == ["messages/gmail-live-lease"]
    log.refresh_from_db()
    assert log.status == EmailIngestionLog.Status.PARTIAL and log.processing_token is None and log.claimed_at is None


@pytest.mark.django_db
def test_gmail_sync_requires_finance_role(finance_client):
    tenant, user, client = finance_client
    user.memberships.filter(tenant=tenant).update(role="AUDITOR")
    response = client.post("/api/v1/google/gmail/sync", {}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert response.status_code == 403


@pytest.mark.django_db
def test_tally_export_applies_workspace_ledgers_and_balances_tds(finance_client):
    import csv
    import io
    from exports_app.models import TallyLedgerMapping
    from exports_app.services import create_tally_csv
    from phase3.models import TaxReview
    tenant, user, client = finance_client
    vendor = Vendor.objects.create(tenant=tenant, name="Mapped vendor", approved=True)
    invoice = Invoice.objects.create(tenant=tenant, vendor=vendor, invoice_number="TALLY-MAPPED-1", category="SERVICES",
        taxable_total="100.00", gst_total="18.00", tds_total="2.00", invoice_total="116.00", status=Invoice.Status.PAYMENT_READY)
    InvoiceLine.objects.create(tenant=tenant, invoice=invoice, line_no=1, description="Service work", quantity="1", rate="100",
        taxable_value="100", gst_rate="18", gst_amount="18", tds_amount="2")
    TaxReview.objects.create(tenant=tenant, invoice=invoice, tds_section="194C")
    mappings = [
        ("VENDOR_LEDGER", str(vendor.id), "Mapped vendor ledger"),
        ("PURCHASE_LEDGER", "services", "Services expense"),
        ("GST_LEDGER", "18", "Input GST 18"),
        ("TDS_LEDGER", "194c", "TDS payable 194C"),
        ("COST_CENTER", "category:services", "Operations"),
        ("VOUCHER_TYPE", "default", "Purchase"),
    ]
    for dimension, key, value in mappings:
        TallyLedgerMapping.objects.create(tenant=tenant, dimension=dimension, source_key=key, ledger_name=value, created_by=user)
    normalized = client.post("/api/v1/tally-mappings", {"dimension": "GST_LEDGER", "source_key": "18.000", "ledger_name": "Input GST 18"}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert normalized.status_code == 200 and TallyLedgerMapping.objects.filter(tenant=tenant, dimension="GST_LEDGER").count() == 1
    other_tenant = Tenant.objects.create(name="Tally mapping isolation", workspace_key="tally-map-isolation")
    other_vendor = Vendor.objects.create(tenant=other_tenant, name="Private vendor", approved=True)
    cross_tenant = client.post("/api/v1/tally-mappings", {"dimension": "VENDOR_LEDGER", "source_key": str(other_vendor.id), "ledger_name": "Private ledger"}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert cross_tenant.status_code == 400
    cross_tenant_cost_center = client.post("/api/v1/tally-mappings", {"dimension": "COST_CENTER", "source_key": f"VENDOR:{other_vendor.id}", "ledger_name": "Private cost center"}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert cross_tenant_cost_center.status_code == 400
    job, body = create_tally_csv(tenant, [invoice], user)
    row = next(csv.DictReader(io.StringIO(body)))
    assert row["Vendor Ledger"] == "Mapped vendor ledger"
    assert row["Purchase Ledger"] == "Services expense"
    assert row["GST Ledger"] == "Input GST 18"
    assert row["TDS Ledger"] == "TDS payable 194C"
    assert row["Cost Center"] == "Operations"
    assert Decimal(row["Total Debit"]) == Decimal(row["Total Credit"]) == Decimal("118.00")
    assert job.debit_total == job.credit_total == Decimal("118.00")
    user.memberships.filter(tenant=tenant).update(role="AUDITOR")
    denied = client.post("/api/v1/tally-mappings", {"dimension": "VOUCHER_TYPE", "source_key": "default", "ledger_name": "Purchase"}, format="json", HTTP_X_WORKSPACE=tenant.workspace_key)
    assert denied.status_code == 403


@pytest.mark.django_db
def test_google_signin_state_is_single_use_and_workspace_scoped(monkeypatch, finance_client):
    from urllib.parse import parse_qs, urlparse, urlsplit
    from django.conf import settings
    from accounts.models import Membership
    from rest_framework_simplejwt.tokens import AccessToken
    tenant, user, _ = finance_client
    started = APIClient().get(f"/api/v1/auth/oauth/google/start?workspace={tenant.workspace_key}")
    assert started.status_code == 200, started.data
    params = parse_qs(urlparse(started.data["authorization_url"]).query)
    assert params["redirect_uri"][0] == "http://localhost:8000/api/v1/auth/oauth/google/callback/"
    assert params["scope"][0] == "openid email profile"
    monkeypatch.setattr("phase3.views.exchange_signin_code", lambda code: {"access_token": "id-check-token"})
    monkeypatch.setattr("phase3.views.get_google_profile", lambda token: {"subject": "google-user-1", "email": user.email})
    callback = APIClient().get(f"/api/v1/auth/oauth/google/callback/?code=single-use&state={params['state'][0]}")
    assert callback.status_code == 302
    fragment = parse_qs(urlsplit(callback["Location"]).fragment)
    assert fragment["workspace"] == [tenant.workspace_key]
    assert AccessToken(fragment["access"][0])["user_id"] == str(user.id)
    replay = APIClient().get(f"/api/v1/auth/oauth/google/callback/?code=single-use&state={params['state'][0]}")
    assert "google_error=authorization_expired" in replay["Location"]
    isolated = Tenant.objects.create(name="Isolated Google workspace", workspace_key="isolated-google")
    other_start = APIClient().get(f"/api/v1/auth/oauth/google/start?workspace={isolated.workspace_key}")
    other_state = parse_qs(urlparse(other_start.data["authorization_url"]).query)["state"][0]
    other_callback = APIClient().get(f"/api/v1/auth/oauth/google/callback/?code=other-workspace-code&state={other_state}")
    assert "google_error=workspace_access_denied" in other_callback["Location"]
    denied_start = APIClient().get("/api/v1/auth/oauth/google/start?workspace=missing-workspace")
    assert denied_start.status_code == 400
