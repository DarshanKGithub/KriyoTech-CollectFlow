from datetime import date
from decimal import Decimal
import pytest
from tenants.models import Tenant
from accounts.models import User
from vendors.models import Vendor
from procurement.models import PurchaseOrder, PurchaseOrderLine, GRN, GRNLine
from invoices.models import Invoice, InvoiceLine
from .services import run_matching

@pytest.mark.django_db
def test_clean_three_way_match_passes():
    tenant = Tenant.objects.create(name="Pilot", workspace_key="pilot")
    user = User.objects.create_user(username="a@b.test", email="a@b.test", password="example-pass")
    vendor = Vendor.objects.create(tenant=tenant, name="Approved Supplier", approved=True)
    po = PurchaseOrder.objects.create(tenant=tenant, vendor=vendor, number="PO-1", order_date=date.today())
    po_line = PurchaseOrderLine.objects.create(tenant=tenant, purchase_order=po, line_no=1, item_code="A1", description="Widget", quantity=Decimal("10"), uom="EA", rate=Decimal("5"), gst_rate=Decimal("18"))
    grn = GRN.objects.create(tenant=tenant, vendor=vendor, purchase_order=po, number="GRN-1")
    GRNLine.objects.create(tenant=tenant, grn=grn, purchase_order_line=po_line, description="Widget", item_code="A1", quantity_received=Decimal("10"), uom="EA")
    invoice = Invoice.objects.create(tenant=tenant, vendor=vendor, invoice_number="INV-1", po_number="PO-1", uploaded_by=user)
    InvoiceLine.objects.create(tenant=tenant, invoice=invoice, line_no=1, item_code="A1", description="Widget", quantity=Decimal("10"), rate=Decimal("5"), gst_rate=Decimal("18"))
    result = run_matching(invoice, user)
    assert result.outcome == "MATCHED"
    invoice.refresh_from_db()
    assert invoice.status == Invoice.Status.MATCHED

@pytest.mark.django_db
def test_matching_flags_rate_and_missing_receipt():
    tenant = Tenant.objects.create(name="Pilot 2", workspace_key="pilot-two")
    vendor = Vendor.objects.create(tenant=tenant, name="Supplier", approved=True)
    po = PurchaseOrder.objects.create(tenant=tenant, vendor=vendor, number="PO-2")
    PurchaseOrderLine.objects.create(tenant=tenant, purchase_order=po, line_no=1, item_code="A2", description="Part", quantity=Decimal("10"), rate=Decimal("10"), gst_rate=Decimal("18"))
    invoice = Invoice.objects.create(tenant=tenant, vendor=vendor, invoice_number="INV-2", po_number="PO-2")
    InvoiceLine.objects.create(tenant=tenant, invoice=invoice, line_no=1, item_code="A2", description="Part", quantity=Decimal("2"), rate=Decimal("12"), gst_rate=Decimal("18"))
    result = run_matching(invoice)
    assert result.outcome == "EXCEPTION"
    assert set(invoice.exceptions.values_list("code", flat=True)) == {"MISSING_GRN", "RATE_VARIANCE", "PARTIAL_DELIVERY"}

@pytest.mark.django_db
def test_same_vendor_invoice_number_is_flagged_without_duplicate_exception_spam():
    tenant = Tenant.objects.create(name="Duplicate Pilot", workspace_key="duplicate-pilot")
    vendor = Vendor.objects.create(tenant=tenant, name="Supplier", approved=True)
    Invoice.objects.create(tenant=tenant, vendor=vendor, invoice_number="INV-77")
    duplicate = Invoice.objects.create(tenant=tenant, vendor=vendor, invoice_number="inv-77")
    run_matching(duplicate)
    run_matching(duplicate)
    assert duplicate.exceptions.filter(code="DUPLICATE_INVOICE", status="OPEN").count() == 1
