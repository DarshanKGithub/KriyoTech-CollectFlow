"""Regressions for the six product-readiness defects identified in the audit."""
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
from types import SimpleNamespace

import pytest
from django.core.files.base import ContentFile
from django.db import connection, connections, close_old_connections
from django.utils import timezone
from rest_framework.test import APIClient
from accounts.models import User, Membership
from documents.models import Document
from exceptions_app.models import InvoiceException
from invoices.models import Invoice, InvoiceLine
from payments.models import Payment, PaymentAllocation
from tenants.models import Tenant
from vendors.models import Vendor
from admin_console.models import Feature, Plan, PlanFeature, Subscription, TenantUsage


@pytest.fixture
def workspace(db, settings):
    settings.EXTRACTION_PROVIDER = "manual"
    runtime = Path(__file__).resolve().parents[2]/".dev-runtime"
    runtime.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="finance-regression-", dir=runtime) as folder:
        assert Path(folder).resolve().is_relative_to(runtime.resolve())
        settings.MEDIA_ROOT = folder
        tenant = Tenant.objects.create(name="Finance regression",workspace_key="finance-regression")
        other = Tenant.objects.create(name="Other company",workspace_key="finance-other")
        user = User.objects.create_user(username="finance-regression",email="finance-regression@example.test")
        Membership.objects.create(tenant=tenant,user=user,role="FINANCE")
        vendor = Vendor.objects.create(tenant=tenant,name="Approved supplier",approved=True)
        client = APIClient();client.force_authenticate(user)
        yield SimpleNamespace(tenant=tenant,other=other,user=user,vendor=vendor,client=client)


def invoice(s, status="PAYMENT_READY", total="100"):
    return Invoice.objects.create(tenant=s.tenant,vendor=s.vendor,status=status,invoice_number="INV-"+uuid.uuid4().hex[:8],invoice_total=total,taxable_total=total)


def payment_payload(inv, amount="100", key=None):
    return {"vendor":str(inv.vendor_id),"amount":amount,"paid_at":str(timezone.localdate()),"mode":"BANK_TRANSFER","reference_number":"TEST-UTR",
        "idempotency_key":str(key or uuid.uuid4()),"allocations":[{"invoice":str(inv.pk),"amount":amount}]}


@pytest.mark.parametrize("relation",["vendor","document"])
@pytest.mark.parametrize("operation",["create","patch"])
def test_foreign_invoice_relationship_rejected(workspace,relation,operation):
    s=workspace
    foreign = Vendor.objects.create(tenant=s.other,name="Private supplier") if relation=="vendor" else Document.objects.create(tenant=s.other,filename="private.pdf",file="private.pdf",media_type="application/pdf",checksum_sha256="c"*64,size_bytes=1)
    payload={relation:str(foreign.pk)}
    if operation=="create": response=s.client.post("/api/v1/invoices/",payload,format="json")
    else:
        inv=invoice(s,"REVIEW_REQUIRED")
        response=s.client.patch(f"/api/v1/invoices/{inv.pk}/",payload,format="json")
    assert response.status_code==400,response.data
    assert relation in response.data


def test_source_and_representation_fail_closed_for_legacy_foreign_links(workspace):
    s=workspace
    vendor=Vendor.objects.create(tenant=s.other,name="Private supplier")
    document=Document.objects.create(tenant=s.other,filename="private.pdf",file="private.pdf",media_type="application/pdf",checksum_sha256="d"*64,size_bytes=1)
    inv=Invoice.objects.create(tenant=s.tenant,vendor=vendor,document=document,status="REVIEW_REQUIRED")
    response=s.client.get(f"/api/v1/invoices/{inv.pk}/source/")
    assert response.status_code==404
    detail=s.client.get(f"/api/v1/invoices/{inv.pk}/")
    assert detail.status_code==200
    assert detail.data["vendor"] is None and detail.data["vendor_name"] is None and detail.data["document"] is None


def test_owned_source_remains_readable(workspace):
    s=workspace
    document=Document.objects.create(tenant=s.tenant,filename="own.pdf",file=ContentFile(b"OWN_TEST_DOCUMENT",name="own.pdf"),media_type="application/pdf",checksum_sha256="e"*64,size_bytes=17)
    inv=Invoice.objects.create(tenant=s.tenant,vendor=s.vendor,document=document,status="REVIEW_REQUIRED")
    response=s.client.get(f"/api/v1/invoices/{inv.pk}/source/")
    assert response.status_code==200
    assert b"".join(response.streaming_content)==b"OWN_TEST_DOCUMENT"
    response.close()


@pytest.mark.parametrize("status",["UPLOADED","EXTRACTING","EXTRACTION_FAILED","REVIEW_REQUIRED","MATCHED","EXCEPTION","APPROVAL_PENDING","APPROVED","REJECTED"])
def test_payment_requires_payment_ready_state(workspace,status):
    s=workspace;inv=invoice(s,status)
    response=s.client.post("/api/v1/payments",payment_payload(inv),format="json")
    assert response.status_code==409,response.data
    assert not Payment.objects.exists()
    inv.refresh_from_db();assert inv.payment_status=="UNPAID"


def test_blocking_exception_prevents_payment(workspace):
    s=workspace;inv=invoice(s)
    InvoiceException.objects.create(tenant=s.tenant,invoice=inv,code="MANUAL_REVIEW",blocking=True)
    response=s.client.post("/api/v1/payments",payment_payload(inv),format="json")
    assert response.status_code==409
    assert not Payment.objects.exists()
    queue = s.client.get("/api/v1/invoices/?payment_queue=1&status__in=PAYMENT_READY,EXPORTED&payment_status__in=UNPAID,PARTIALLY_PAID")
    assert queue.status_code == 200
    assert queue.data["results"][0]["payment_hold"] == "blocking_exception"


def test_invalid_amount_and_key_return_validation_errors_not_server_errors(workspace):
    s=workspace;inv=invoice(s)
    for invalid in ("0","-1"):
        response=s.client.post("/api/v1/payments",payment_payload(inv,invalid),format="json")
        assert response.status_code==400
    payload=payment_payload(inv);payload["idempotency_key"]="not-a-uuid"
    assert s.client.post("/api/v1/payments",payload,format="json").status_code==400
    payload=payment_payload(inv);payload["allocations"]=[]
    assert s.client.post("/api/v1/payments",payload,format="json").status_code==400


def test_partial_payment_replay_and_changed_payload_conflict(workspace):
    s=workspace;inv=invoice(s);payload=payment_payload(inv,"40")
    first=s.client.post("/api/v1/payments",payload,format="json")
    assert first.status_code==201,first.data
    inv.refresh_from_db();assert inv.payment_status=="PARTIALLY_PAID"
    queue_url = "/api/v1/invoices/?payment_queue=1&status__in=PAYMENT_READY,EXPORTED&payment_status__in=UNPAID,PARTIALLY_PAID"
    queue = s.client.get(queue_url)
    assert queue.status_code == 200
    row, = queue.data["results"]
    assert row["id"] == str(inv.id) and row["outstanding_balance"] == "60.00"
    assert row["payment_hold"] is None
    replay=s.client.post("/api/v1/payments",payload,format="json")
    assert replay.status_code==200 and replay.data["id"]==first.data["id"]
    changed=payment_payload(inv,"30",payload["idempotency_key"])
    assert s.client.post("/api/v1/payments",changed,format="json").status_code==409
    assert Payment.objects.count()==1
    final=s.client.post("/api/v1/payments",payment_payload(inv,"60"),format="json")
    assert final.status_code==201,final.data
    inv.refresh_from_db();assert inv.payment_status=="PAID"
    assert sum(inv.payment_allocations.values_list("amount",flat=True))==100
    assert s.client.get(queue_url).data["results"] == []


def test_duplicate_invoice_allocations_are_combined_before_balance_check(workspace):
    s=workspace;inv=invoice(s);payload=payment_payload(inv,"120")
    payload["allocations"]=[{"invoice":str(inv.id),"amount":"60"},{"invoice":str(inv.id),"amount":"60"}]
    assert s.client.post("/api/v1/payments",payload,format="json").status_code==409
    assert not Payment.objects.exists()


def test_payment_can_use_exported_invoice_but_not_another_company(workspace):
    s=workspace;inv=invoice(s,"EXPORTED")
    assert s.client.post("/api/v1/payments",payment_payload(inv),format="json").status_code==201
    foreign_vendor=Vendor.objects.create(tenant=s.other,name="Other supplier",approved=True)
    foreign=Invoice.objects.create(tenant=s.other,vendor=foreign_vendor,status="PAYMENT_READY",invoice_total=100)
    assert s.client.post("/api/v1/payments",payment_payload(foreign),format="json").status_code==400


@pytest.mark.parametrize("state",["APPROVAL_PENDING","APPROVED","PAYMENT_READY","EXPORTED"])
def test_protected_invoice_cannot_be_edited_deleted_or_reextracted(workspace,state,settings):
    s=workspace;inv=invoice(s,state)
    url=f"/api/v1/invoices/{inv.id}/"
    response=s.client.patch(url,{"invoice_total":"1","financial_locked_at":None},format="json")
    assert response.status_code==409,response.data
    assert s.client.delete(url).status_code==409
    settings.EXTRACTION_PROVIDER="test"
    assert s.client.post(url+"extract/",{},format="json").status_code==409
    assert s.client.post(url+"confirm-extraction/",{},format="json").status_code==409
    inv.refresh_from_db();assert inv.invoice_total==100 and inv.status==state


def test_financial_lock_survives_status_reset_and_paid_allocations_remain_unchanged(workspace):
    s=workspace;inv=invoice(s,"EXPORTED")
    payment=Payment.objects.create(tenant=s.tenant,vendor=s.vendor,amount=100,paid_at=timezone.localdate())
    PaymentAllocation.objects.create(tenant=s.tenant,payment=payment,invoice=inv,amount=100)
    Invoice.objects.filter(pk=inv.pk).update(status="REVIEW_REQUIRED")
    response=s.client.patch(f"/api/v1/invoices/{inv.id}/",{"invoice_total":"1"},format="json")
    assert response.status_code==409
    inv.refresh_from_db();assert inv.invoice_total==100 and inv.financial_locked_at
    assert inv.payment_allocations.get().amount==100


def test_unposted_invoice_corrections_work_but_payment_flag_is_read_only(workspace):
    s=workspace;inv=invoice(s,"REVIEW_REQUIRED")
    response=s.client.patch(f"/api/v1/invoices/{inv.pk}/",{"supplier_name":"Corrected","payment_status":"PAID"},format="json")
    assert response.status_code==200,response.data
    inv.refresh_from_db();assert inv.supplier_name=="Corrected" and inv.payment_status=="UNPAID"


def test_fleet_alerts_work_empty_and_populated(workspace):
    from fleet.models import FleetVehicle,FleetDriver,FleetTrip
    s=workspace
    assert s.client.get("/api/v1/fleet/alerts").status_code==200
    vehicle=FleetVehicle.objects.create(tenant=s.tenant,registration_number="KA01AA1000",normalized_registration="KA01AA1000")
    driver=FleetDriver.objects.create(tenant=s.tenant,name="Test driver")
    FleetTrip.objects.create(tenant=s.tenant,vehicle=vehicle,driver=driver,trip_number="TRIP-TEST",status="IN_PROGRESS")
    response=s.client.get("/api/v1/fleet/alerts")
    assert response.status_code==200,response.data
    assert isinstance(response.data["alerts"],list)


@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(connection.vendor!="postgresql",reason="Requires real PostgreSQL row locks")
@pytest.mark.parametrize("scenario",["different_keys","same_key","same_key_different_invoices","reversed_invoice_order"])
def test_concurrent_payments_are_serialized_on_postgresql(workspace,monkeypatch,scenario):
    from invoices import phase2
    s=workspace;first=invoice(s)
    a=payment_payload(first,"60")
    b=payment_payload(first,"60",a["idempotency_key"] if scenario=="same_key" else None)
    if scenario=="same_key_different_invoices":
        second=invoice(s);b=payment_payload(second,"60",a["idempotency_key"])
    if scenario=="reversed_invoice_order":
        second=invoice(s)
        a["amount"]=b["amount"]="120"
        a["allocations"]=[{"invoice":str(first.id),"amount":"60"},{"invoice":str(second.id),"amount":"60"}]
        b["allocations"]=list(reversed(a["allocations"]))
    gate=Barrier(2)
    original=phase2.record_payment
    def synchronized(**kwargs):
        gate.wait(timeout=20)
        return original(**kwargs)
    monkeypatch.setattr(phase2,"record_payment",synchronized)
    def send(payload):
        close_old_connections()
        try:
            client=APIClient();client.force_authenticate(s.user)
            response=client.post("/api/v1/payments",payload,format="json")
            return response.status_code
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as workers:
        futures=[workers.submit(send,payload) for payload in (a,b)]
        statuses=sorted(future.result(timeout=40) for future in futures)
    assert statuses==([200,201] if scenario=="same_key" else [201,409])
    assert Payment.objects.count()==1
    assert all(sum(inv.payment_allocations.values_list("amount",flat=True))<=inv.invoice_total for inv in Invoice.objects.filter(tenant=s.tenant))


@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(connection.vendor!="postgresql",reason="Requires PostgreSQL row locks")
def test_concurrent_invoice_intake_observes_one_shared_quota(workspace):
    from rest_framework.exceptions import PermissionDenied
    s=workspace
    plan=Plan.objects.create(name="Quota one",slug="quota-one",invoice_limit=1)
    feature=Feature.objects.create(key="invoice_upload",name="Invoice upload")
    PlanFeature.objects.create(plan=plan,feature=feature,enabled=True)
    Subscription.objects.create(tenant=s.tenant,plan=plan,status=Subscription.Status.ACTIVE)
    gate=Barrier(2)
    def create_invoice():
        close_old_connections()
        try:
            gate.wait(timeout=15)
            try:
                Invoice.objects.create(tenant=s.tenant)
                return "created"
            except PermissionDenied:
                return "quota_rejected"
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as workers:
        results=sorted(workers.map(lambda _: create_invoice(), range(2)))
    assert results==["created","quota_rejected"]
    assert TenantUsage.objects.get(tenant=s.tenant,metric="invoices_uploaded").used_count==1


@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(connection.vendor!="postgresql",reason="PostgreSQL nullable-join regression")
def test_trip_actions_and_customer_billing_on_postgresql(workspace):
    from fleet.models import FleetCustomer,FleetVehicle,FleetDriver,FleetTrip,TransportOrder
    s=workspace
    vehicle=FleetVehicle.objects.create(tenant=s.tenant,registration_number="KA01AA2000",normalized_registration="KA01AA2000")
    driver=FleetDriver.objects.create(tenant=s.tenant,name="Driver")
    unlinked=FleetTrip.objects.create(tenant=s.tenant,vehicle=vehicle,driver=driver,trip_number="UNLINKED")
    response=s.client.post(f"/api/v1/fleet/trips/{unlinked.id}/start",{},format="json")
    assert response.status_code==200,response.data
    response=s.client.post("/api/v1/fleet/customer-invoices",{"trip_id":str(unlinked.id)},format="json")
    assert response.status_code==400,response.data
    customer=FleetCustomer.objects.create(tenant=s.tenant,name="Customer")
    order=TransportOrder.objects.create(tenant=s.tenant,customer=customer,order_number="ORDER-TEST",status="DELIVERED",agreed_amount=1000)
    trip=FleetTrip.objects.create(tenant=s.tenant,vehicle=vehicle,driver=driver,trip_number="DELIVERED",transport_order=order,delivery_at=timezone.now(),delivery_signature_name="Receiver",status="COMPLETED")
    response=s.client.post("/api/v1/fleet/customer-invoices",{"trip_id":str(trip.id)},format="json")
    assert response.status_code==201,response.data
