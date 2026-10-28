import json
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from cryptography.fernet import Fernet
from django.utils import timezone
from rest_framework.test import APIClient
from accounts.models import Membership, User
from tenants.models import Tenant
from vendors.models import Vendor
from invoices.models import Invoice, InvoiceLine
from payments.models import Payment
from .adapters import ERPNext, DynamicsFinance, ZohoBooks, ZohoInventory, Tally, safe_xml
from .models import ERPConnection, ERPRecord, ERPSyncRun
from .records import apply_inbound, snapshot
from .security import ERPError, credentials, encrypt, validate_origin
from .tasks import pull_records, recover_stalled_jobs
from .outbound import payload_for, tally_xml


@pytest.fixture
def setup(db, settings):
    settings.ERP_CREDENTIALS_KEY = Fernet.generate_key().decode()
    tenant = Tenant.objects.create(name="ERP tenant", workspace_key="erp-tenant")
    user = User.objects.create_user(username="erp-owner", email="erp@example.test")
    Membership.objects.create(tenant=tenant, user=user, role="OWNER")
    client = APIClient(); client.force_authenticate(user)
    connection = ERPConnection.objects.create(tenant=tenant, provider="ERPNEXT", name="ERPNext sandbox", config={"base_url": "https://erp.example.test", "company": "ERP tenant"}, encrypted_credentials=encrypt({"api_key": "key-private", "api_secret": "secret-private"}), enabled=True, created_by=user)
    return SimpleNamespace(tenant=tenant,user=user,client=client,connection=connection)


def supplier_record(s):
    return ERPRecord.objects.create(connection=s.connection, resource="suppliers", external_id="SUP-001", payload={"supplier_name": "Supplier"})


def invoice_ready(s):
    vendor = Vendor.objects.create(tenant=s.tenant,name="Mapped vendor",approved=True)
    ERPRecord.objects.create(connection=s.connection,resource="suppliers",external_id="SUP-ERP",local_id=vendor.pk,status="APPLIED",payload={"supplier_name":"Mapped vendor"})
    invoice=Invoice.objects.create(tenant=s.tenant,vendor=vendor,invoice_number="INV-1",invoice_date=timezone.localdate(),status="PAYMENT_READY",taxable_total=100,invoice_total=100)
    InvoiceLine.objects.create(tenant=s.tenant,invoice=invoice,line_no=1,description="Service",quantity=1,rate=100,taxable_value=100,item_code="LOCAL")
    s.connection.config["item_map"]={"LOCAL":"REMOTE"};s.connection.save()
    return invoice


def prepare(s, invoice):
    response=s.client.post("/api/v1/erp/records",{"connection_id":str(s.connection.id),"resource":"invoices","local_id":str(invoice.id)},format="json")
    assert response.status_code==201,response.data
    return ERPRecord.objects.get(pk=response.data["id"])


def test_saved_secrets_encrypted_and_absent_from_api(setup):
    s=setup
    assert "secret-private" not in s.connection.encrypted_credentials
    assert credentials(s.connection)["api_secret"]=="secret-private"
    response=s.client.get("/api/v1/erp/connections")
    assert response.status_code==200
    assert "secret-private" not in json.dumps(response.data)
    assert "encrypted_credentials" not in json.dumps(response.data)


def test_cross_tenant_and_purchase_role_cannot_manage_connections(setup):
    s=setup
    other=Tenant.objects.create(name="Other",workspace_key="erp-other")
    external=ERPConnection.objects.create(tenant=other,provider="TALLY",name="Other",config={})
    assert s.client.post(f"/api/v1/erp/connections/{external.id}/test",{},format="json").status_code==404
    membership=Membership.objects.get(tenant=s.tenant,user=s.user);membership.role="PURCHASE";membership.save()
    assert s.client.get("/api/v1/erp/connections").status_code==403


def test_connection_edit_invalidates_verification_but_retains_blank_secrets(setup):
    s=setup
    response=s.client.patch(f"/api/v1/erp/connections/{s.connection.id}",{"name":"Changed","credentials":{"api_secret":""}},format="json")
    assert response.status_code==201,response.data
    s.connection.refresh_from_db()
    assert not s.connection.enabled
    assert credentials(s.connection)["api_secret"]=="secret-private"


def test_test_does_not_enable_a_connection_changed_during_network_call(setup,monkeypatch):
    s=setup
    def changed():
        s.connection.name="Changed mid-test";s.connection.save()
        return "OK"
    monkeypatch.setattr("erp.views.adapter",lambda connection:SimpleNamespace(test=changed))
    response=s.client.post(f"/api/v1/erp/connections/{s.connection.id}/test",{},format="json")
    assert response.status_code==400


def test_pull_duplicate_delivery_is_idempotent_and_changes_become_conflicts(setup,monkeypatch):
    s=setup
    provider=Mock(return_value=([("SUP-001",{"supplier_name":"Supplier"})],False))
    monkeypatch.setattr("erp.tasks.adapter",lambda connection:SimpleNamespace(pull=provider))
    run=ERPSyncRun.objects.create(connection=s.connection,resource="suppliers",requested_by=s.user)
    assert pull_records(str(run.id))=="COMPLETED"
    assert pull_records(str(run.id))=="COMPLETED"
    assert provider.call_count==1
    record=ERPRecord.objects.get(connection=s.connection,external_id="SUP-001")
    local=apply_inbound(record,{"name":"Supplier"},s.user)
    provider.return_value=([("SUP-001",{"supplier_name":"Changed remote supplier"})],False)
    next_run=ERPSyncRun.objects.create(connection=s.connection,resource="suppliers")
    assert pull_records(str(next_run.id))=="COMPLETED"
    record.refresh_from_db();local.refresh_from_db()
    assert record.status=="CONFLICT"
    assert local.name=="Supplier"


def test_supplier_import_never_grants_approval_and_cannot_apply_twice(setup):
    s=setup;record=supplier_record(s)
    vendor=apply_inbound(record,{"name":"Supplier","approved":True},s.user)
    assert not vendor.approved
    with pytest.raises(ERPError):apply_inbound(record,{"name":"Supplier"},s.user)
    assert Vendor.objects.filter(tenant=s.tenant).count()==1


def test_cross_tenant_local_link_is_rejected(setup):
    s=setup;record=supplier_record(s)
    other=Tenant.objects.create(name="Other",workspace_key="link-other")
    vendor=Vendor.objects.create(tenant=other,name="Private")
    with pytest.raises(ERPError):apply_inbound(record,{"local_id":str(vendor.pk)},s.user)
    record.refresh_from_db();assert record.local_id is None


def test_unapproved_invoice_cannot_prepare_and_source_change_blocks_send(setup):
    s=setup;invoice=invoice_ready(s)
    invoice.status="REVIEW_REQUIRED";invoice.save()
    response=s.client.post("/api/v1/erp/records",{"connection_id":str(s.connection.id),"resource":"invoices","local_id":str(invoice.id)},format="json")
    assert response.status_code==400
    invoice.status="PAYMENT_READY";invoice.save()
    record=prepare(s,invoice)
    invoice.invoice_total=101;invoice.save()
    response=s.client.post(f"/api/v1/erp/records/{record.id}/send",{"confirm_send":True},format="json")
    assert response.status_code==400


def test_network_timeout_fences_outbound_without_a_second_financial_post(setup,monkeypatch):
    s=setup;record=prepare(s,invoice_ready(s))
    send=Mock(side_effect=ERPError("ERP connection failed."))
    monkeypatch.setattr("erp.views.adapter",lambda connection:SimpleNamespace(send=send))
    url=f"/api/v1/erp/records/{record.id}/send"
    assert s.client.post(url,{"confirm_send":True},format="json").status_code==409
    record.refresh_from_db();assert record.status=="UNKNOWN"
    assert s.client.post(url,{"confirm_send":True},format="json").status_code==400
    assert send.call_count==1


def test_successful_send_requires_confirmation_and_stores_remote_id_once(setup,monkeypatch):
    s=setup;record=prepare(s,invoice_ready(s))
    send=Mock(return_value="PINV-001")
    monkeypatch.setattr("erp.views.adapter",lambda connection:SimpleNamespace(send=send))
    url=f"/api/v1/erp/records/{record.id}/send"
    assert s.client.post(url,{},format="json").status_code==400
    assert s.client.post(url,{"confirm_send":True},format="json").status_code==200
    assert s.client.post(url,{"confirm_send":True},format="json").status_code==400
    record.refresh_from_db();assert record.external_id=="PINV-001" and record.status=="SENT"
    assert send.call_count==1


def test_erpnext_outbound_stays_draft_and_uses_configured_company(setup,monkeypatch):
    s=setup;mock=Mock(return_value={"data":{"name":"PINV-001"}})
    monkeypatch.setattr("erp.adapters.request",mock)
    assert ERPNext(s.connection).send("invoices",{"company":"Other","docstatus":1})=="PINV-001"
    payload=json.loads(mock.call_args.args[3])
    assert payload["docstatus"]==0 and payload["company"]==s.connection.config["company"]


def test_private_origins_require_operator_allowlist_and_dns_is_pinned(setup,settings,monkeypatch):
    monkeypatch.setattr("erp.security.socket.getaddrinfo",lambda *a,**k:[(2,1,6,"",("127.0.0.1",9000))])
    settings.ERP_TRUSTED_ORIGINS=[]
    with pytest.raises(ERPError):validate_origin("http://127.0.0.1:9000")
    with pytest.raises(ERPError):validate_origin("https://public.example.test")
    settings.ERP_TRUSTED_ORIGINS=["http://127.0.0.1:9000"]
    parsed,address=validate_origin("http://127.0.0.1:9000")
    assert address=="127.0.0.1" and parsed.port==9000


@pytest.mark.parametrize("encoding",["utf-8","utf-16"])
def test_xml_entities_are_rejected_for_both_encodings(encoding):
    with pytest.raises(ERPError):safe_xml('<!DOCTYPE test [<!ENTITY hidden "value">]><test>&hidden;</test>'.encode(encoding))


def test_finance_legal_entity_mismatch_cannot_enter_inbox(setup,monkeypatch):
    s=setup;s.connection.provider="DYNAMICS_FINANCE";s.connection.config={"base_url":"https://finance.example.test","legal_entity":"IN01","entities":{"suppliers":{"collection":"VendorsV2","key_fields":["dataAreaId","VendorAccountNumber"]}}}
    provider=DynamicsFinance(s.connection)
    monkeypatch.setattr(provider,"json",lambda path:{"value":[{"dataAreaId":"OTHER","VendorAccountNumber":"X"}]})
    with pytest.raises(ERPError):provider.pull("suppliers",1)


def test_zoho_refresh_uses_matching_data_centre_and_header_token(setup,monkeypatch):
    s=setup;s.connection.provider="ZOHO_BOOKS";s.connection.config={"region":"in","organization_id":"123","client_id":"client"};s.connection.encrypted_credentials=encrypt({"client_secret":"secret","refresh_token":"refresh"})
    request=Mock(return_value={"access_token":"access","expires_in":3600})
    monkeypatch.setattr("erp.adapters.request",request)
    headers=ZohoBooks(s.connection).headers()
    assert request.call_args.args[0]=="https://accounts.zoho.in/oauth/v2/token"
    assert headers["Authorization"]=="Zoho-oauthtoken access"


def test_imported_payment_cannot_overpay_or_double_apply(setup):
    s=setup;invoice=invoice_ready(s)
    record=ERPRecord.objects.create(connection=s.connection,resource="payments",external_id="PAY-ERP",payload={})
    data={"vendor_id":str(invoice.vendor_id),"paid_at":str(timezone.localdate()),"source_posted":True,"amount":"101","allocations":[{"invoice_id":str(invoice.id),"amount":"101"}]}
    with pytest.raises(ERPError):apply_inbound(record,data,s.user)
    assert not Payment.objects.exists()
    data["amount"]="100";data["allocations"][0]["amount"]="100"
    apply_inbound(record,data,s.user)
    with pytest.raises(ERPError):apply_inbound(record,data,s.user)
    invoice.refresh_from_db();assert invoice.payment_status=="PAID"
    assert Payment.objects.count()==1


def test_stalled_sends_require_reconciliation_not_automatic_retry(setup):
    s=setup;record=prepare(s,invoice_ready(s));record.status="SENDING";record.save()
    ERPRecord.objects.filter(pk=record.pk).update(updated_at=timezone.now()-timedelta(minutes=20))
    recover_stalled_jobs()
    record.refresh_from_db();assert record.status=="UNKNOWN"


def test_finance_invoice_header_and_lines_sent_as_one_changeset(setup,monkeypatch):
    s=setup;invoice=invoice_ready(s)
    s.connection.provider="DYNAMICS_FINANCE"
    s.connection.config={"base_url":"https://finance.example.test","legal_entity":"IN01","document_maps":{"invoices":{"header_collection":"VendorInvoiceHeaders","line_collection":"VendorInvoiceLines","external_reference":"{{source.id}}","header":{"HeaderReference":"{{source.id}}","InvoiceNumber":"{{source.invoice_number}}"},"line":{"HeaderReference":"{{source.id}}","InvoiceLineNumber":"{{line_number}}","NetAmount":"{{line.taxable_value}}"}}}}
    source,target=payload_for(s.connection,"invoices",invoice)
    assert len(target["operations"])==2
    for operation in target["operations"]:assert operation["body"]["dataAreaId"]=="IN01"
    transport=Mock(return_value=b"HTTP/1.1 201 Created\r\n{}\r\nHTTP/1.1 201 Created\r\n{}")
    monkeypatch.setattr("erp.adapters.request",transport)
    provider=DynamicsFinance(s.connection);monkeypatch.setattr(provider,"headers",lambda:{"Authorization":"Bearer test"})
    assert provider.send("invoices",target)==str(invoice.id)
    assert transport.call_args.args[0].endswith("/data/$batch")
    body=transport.call_args.args[3].decode()
    assert "VendorInvoiceHeaders" in body and "VendorInvoiceLines" in body
    assert body.count("Content-ID:")==2
    transport.return_value=b"HTTP/1.1 400 Bad Request"
    with pytest.raises(ERPError):provider.send("invoices",target)


def test_tally_xml_is_balanced_escaped_and_has_stable_remote_id(setup):
    s=setup;invoice=invoice_ready(s)
    s.connection.provider="TALLY";s.connection.config={"company":"Transport & Co","defaults":{"invoices":{"purchase_ledger":"Purchases <Goods>"}}}
    ERPRecord.objects.filter(connection=s.connection,resource="suppliers").update(payload={"NAME":"Supplier & Co"})
    source,target=payload_for(s.connection,"invoices",invoice)
    record=ERPRecord.objects.create(connection=s.connection,resource="invoices",direction="OUTBOUND",local_id=invoice.id,payload={"source":source,"target":target})
    raw=tally_xml(record)
    root=safe_xml(raw)
    amounts=[Decimal(node.text) for node in root.iter("AMOUNT")]
    assert sum(amounts)==0
    assert root.find(".//VOUCHER").attrib["REMOTEID"]==str(record.id)
    assert b"&amp;" in raw and b"&lt;Goods&gt;" in raw


def test_tally_success_is_not_inferred_from_http_200(setup,monkeypatch):
    s=setup;s.connection.provider="TALLY";provider=Tally(s.connection)
    transport=Mock(return_value=b"<RESPONSE><CREATED>0</CREATED><ERRORS>1</ERRORS></RESPONSE>")
    monkeypatch.setattr("erp.adapters.request",transport)
    with pytest.raises(ERPError):provider.send("invoices",{"xml":"<ENVELOPE/>","external_reference":"stable"})
    transport.return_value=b"<RESPONSE><CREATED>1</CREATED><ERRORS>0</ERRORS></RESPONSE>"
    assert provider.send("invoices",{"xml":"<ENVELOPE/>","external_reference":"stable"})=="stable"


def test_late_import_result_cannot_overwrite_a_released_job(setup,monkeypatch):
    s=setup;run=ERPSyncRun.objects.create(connection=s.connection,resource="suppliers")
    def response(resource,page):
        ERPSyncRun.objects.filter(pk=run.pk).update(status="FAILED")
        return [("NEW",{"supplier_name":"Late"})],False
    monkeypatch.setattr("erp.tasks.adapter",lambda connection:SimpleNamespace(pull=response))
    assert pull_records(str(run.id))=="STALE_RESULT_IGNORED"
    assert not ERPRecord.objects.filter(external_id="NEW").exists()


def test_background_import_stops_when_finance_access_is_revoked(setup,monkeypatch):
    s=setup
    Membership.objects.filter(tenant=s.tenant,user=s.user).update(is_active=False)
    run=ERPSyncRun.objects.create(connection=s.connection,resource="suppliers",requested_by=s.user)
    transport=Mock()
    monkeypatch.setattr("erp.tasks.adapter",transport)
    assert pull_records(str(run.id))=="FAILED"
    transport.assert_not_called()


def test_branch_scoped_members_cannot_read_company_wide_erp_records(setup):
    s=setup
    Membership.objects.filter(tenant=s.tenant,user=s.user).update(branch_scope_enabled=True)
    assert s.client.get("/api/v1/erp/connections").status_code==403


def test_conflict_acknowledgement_preserves_approved_local_history(setup):
    s=setup;invoice=invoice_ready(s)
    record=ERPRecord.objects.create(connection=s.connection,resource="invoices",external_id="REMOTE-CHANGED",local_id=invoice.id,status="CONFLICT",payload={"grand_total":999})
    response=s.client.post(f"/api/v1/erp/records/{record.id}/review-conflict",{"note":"Reviewed with accountant; retaining original pending correction."},format="json")
    assert response.status_code==200,response.data
    record.refresh_from_db();invoice.refresh_from_db()
    assert record.status=="ACKNOWLEDGED"
    assert invoice.invoice_total==100 and invoice.status=="PAYMENT_READY"


def test_export_candidates_are_approved_and_scoped_to_workspace(setup):
    s=setup
    approved=Vendor.objects.create(tenant=s.tenant,name="Approved",approved=True)
    Vendor.objects.create(tenant=s.tenant,name="Not approved",approved=False)
    other=Tenant.objects.create(name="Other",workspace_key="candidate-other")
    Vendor.objects.create(tenant=other,name="Private",approved=True)
    response=s.client.get("/api/v1/erp/local-records?resource=suppliers")
    assert response.status_code==200
    assert [row["id"] for row in response.data["results"]]==[str(approved.pk)]


def test_inventory_receipt_uses_purchase_order_query_and_returned_receive_id(setup,monkeypatch):
    s=setup;s.connection.provider="ZOHO_INVENTORY";s.connection.config={"region":"in","organization_id":"123","client_id":"client"}
    provider=ZohoInventory(s.connection)
    transport=Mock(return_value={"purchase_receive":{"receive_id":"RECEIVE-1"}})
    monkeypatch.setattr(provider,"api",transport)
    assert provider.send("receipts",{"purchaseorder_id":"PO-REMOTE","receive_number":"GRN-1","line_items":[{"line_item_id":"LINE-REMOTE","quantity":2}]})=="RECEIVE-1"
    assert transport.call_args.args[0]=="/purchasereceives"
    assert transport.call_args.args[3]=={"purchaseorder_id":"PO-REMOTE"}
    assert "purchaseorder_id" not in transport.call_args.args[2]
    assert "/inventory/v1" in provider.base
    with pytest.raises(ERPError):provider.send("invoices",{})


def test_inventory_receipt_preparation_uses_explicit_local_to_remote_po_lines(setup):
    from procurement.models import PurchaseOrder,PurchaseOrderLine,GRN,GRNLine
    s=setup
    vendor=Vendor.objects.create(tenant=s.tenant,name="Receipt vendor")
    po=PurchaseOrder.objects.create(tenant=s.tenant,vendor=vendor,number="PO-1",status="APPROVED")
    line=PurchaseOrderLine.objects.create(tenant=s.tenant,purchase_order=po,line_no=1,description="Goods",quantity=3,rate=100)
    receipt=GRN.objects.create(tenant=s.tenant,vendor=vendor,purchase_order=po,number="GRN-1",received_at=timezone.localdate(),quality_status="ACCEPTED")
    GRNLine.objects.create(tenant=s.tenant,grn=receipt,purchase_order_line=line,description="Goods",quantity_received=2)
    ERPRecord.objects.create(connection=s.connection,resource="purchase_orders",external_id="PO-REMOTE",local_id=po.id,status="APPLIED",payload={})
    s.connection.provider="ZOHO_INVENTORY";s.connection.config={"receipt_line_map":{str(line.id):"LINE-REMOTE"}}
    source,target=payload_for(s.connection,"receipts",receipt)
    assert target["purchaseorder_id"]=="PO-REMOTE"
    assert target["line_items"]==[{"line_item_id":"LINE-REMOTE","quantity":2}]
    s.connection.config["receipt_line_map"]={}
    with pytest.raises(ERPError):payload_for(s.connection,"receipts",receipt)
