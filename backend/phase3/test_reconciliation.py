import uuid
from datetime import date
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from django.db import connection, connections, close_old_connections
from rest_framework.test import APIClient
from accounts.models import User, Membership
from tenants.models import Tenant
from vendors.models import Vendor
from payments.models import Payment
from settlements.models import SourceAccount
from .models import (BankStatement, BankTransaction, ReconciliationRun, ReconciliationCandidate,
    ReconciliationReview, ReconciliationGroup, ReconciliationGroupTarget)

URL="/api/v1/bank-reconciliation"


@pytest.fixture
def env(db):
    tenant=Tenant.objects.create(name="Reconciliation",workspace_key="reviewed-bank")
    user=User.objects.create_user(username="reviewer",email="reviewer@bank.test")
    member=Membership.objects.create(tenant=tenant,user=user,role="FINANCE")
    client=APIClient();client.force_authenticate(user)
    account=SourceAccount.objects.create(scope="TENANT",tenant=tenant,kind="BANK",provider="BANK",name="Bank",external_reference="1234",currency="INR")
    statement=BankStatement.objects.create(tenant=tenant,filename="bank.csv",content_hash="bank",source_account=account,currency="INR")
    vendor=Vendor.objects.create(tenant=tenant,name="Supplier",approved=True)
    return locals()


def bank(s,amount="-100.00",reference="UTR-1234",**kwargs):
    return BankTransaction.objects.create(tenant=s["tenant"],statement=s["statement"],transaction_date=date.today(),
        description="Supplier transfer",amount=amount,reference=reference,fingerprint=uuid.uuid4().hex,**kwargs)


def payment(s,amount="100.00",reference="UTR-1234",**kwargs):
    return Payment.objects.create(tenant=s["tenant"],vendor=s["vendor"],source_account=s["account"],currency="INR",
        paid_at=date.today(),amount=amount,reference_number=reference,**kwargs)


def patch(s,**data): return s["client"].patch(URL,data,format="json")


def group_payload(banks,items,**kwargs):
    return {"action":"group_match","request_key":str(uuid.uuid4()),"reason":"Verified exact shared UTR on original evidence",
        "bank_ids":[str(item.pk) for item in banks],"targets":[{"target_type":"VENDOR_PAYMENT","target_id":str(item.pk)} for item in items],
        "components":{"fees":"0.00","fee_tax":"0.00","refunds":"0.00","adjustments":"0.00"},**kwargs}


def test_saved_run_reuse_normalization_reject_and_stale_evidence(env):
    row=bank(env);item=payment(env,reference="utr １２３４")
    first=env["client"].get(URL+"?suggestions_for="+str(row.pk))
    assert first.status_code == 200,first.data
    candidate=first.data["suggestions"][0]
    assert "EXACT_NORMALIZED_REFERENCE" in candidate["reason_codes"]
    again=env["client"].get(URL+"?suggestions_for="+str(row.pk))
    assert first.data["run_id"] == again.data["run_id"] and ReconciliationRun.objects.count() == 1
    reject={"action":"reject_candidate","transaction_id":str(row.pk),"candidate_id":candidate["candidate_id"],"reason":"Reference belongs to a different supplier transfer","request_key":str(uuid.uuid4()),"expected_revision":0}
    assert patch(env,**reject).status_code == 200
    assert patch(env,**reject).status_code == 200
    assert ReconciliationReview.objects.count() == 1
    data={"action":"match","transaction_id":str(row.pk),"candidate_id":candidate["candidate_id"],"target_type":"VENDOR_PAYMENT","target_id":str(item.pk)}
    assert patch(env,**data).status_code == 409
    Payment.objects.filter(pk=item.pk).update(reference_number="UTR-CHANGED")
    assert patch(env,**data).status_code == 409
    assert env["client"].get(URL+"?suggestions_for="+str(row.pk)).data["run_id"] != first.data["run_id"]
    history=env["client"].get(URL+"?history_for="+str(row.pk)).data
    assert history["events"][0]["action"] == "REJECT"


def test_accept_confirm_clear_are_audited_revision_checked_and_idempotent(env):
    row=bank(env);item=payment(env)
    candidate=env["client"].get(URL+"?suggestions_for="+str(row.pk)).data["suggestions"][0]
    request={"action":"match","transaction_id":str(row.pk),"candidate_id":candidate["candidate_id"],"target_type":"VENDOR_PAYMENT","target_id":str(item.pk),"expected_revision":0,"request_key":str(uuid.uuid4())}
    assert patch(env,**request).status_code == 200
    assert patch(env,**request).status_code == 200
    assert patch(env,**{**request,"reason":"Changed request using the same key"}).status_code == 409
    assert patch(env,action="reconcile",transaction_id=str(row.pk),expected_revision=0).status_code == 409
    assert patch(env,action="reconcile",transaction_id=str(row.pk),expected_revision=1).status_code == 200
    assert patch(env,action="unmatch",transaction_id=str(row.pk)).status_code == 400
    assert patch(env,action="unmatch",transaction_id=str(row.pk),expected_revision=2,reason="Correcting a mistaken link").status_code == 200
    assert list(ReconciliationReview.objects.order_by("created_at").values_list("action",flat=True)) == ["ACCEPT","CONFIRM","CLEAR"]
    row.refresh_from_db();assert row.revision == 3 and row.payment_id is None


def test_ambiguous_and_missing_reference_candidates_never_confirm_automatically(env):
    row=bank(env,reference="");payment(env,reference="");payment(env,reference="")
    data=env["client"].get(URL+"?suggestions_for="+str(row.pk)).data
    assert data["ambiguous"] and len(data["suggestions"]) == 2
    assert all("EXACT_NORMALIZED_REFERENCE" not in item["reason_codes"] for item in data["suggestions"])
    row.refresh_from_db();assert row.status == "UNMATCHED"


@pytest.mark.parametrize("split",[True,False])
def test_supported_groups_confirm_clear_and_preserve_history(env,split):
    banks=[bank(env,"-60"),bank(env,"-40")] if split else [bank(env)]
    items=[payment(env)] if split else [payment(env,"60"),payment(env,"40")]
    request=group_payload(banks,items)
    result=patch(env,**request);assert result.status_code == 200,result.data
    group_id=result.data["id"]
    assert patch(env,**request).data["id"] == group_id and ReconciliationGroup.objects.count() == 1
    assert patch(env,action="unmatch",transaction_id=str(banks[0].pk),reason="Cannot clear one member").status_code == 409
    confirm={"action":"group_confirm","group_id":group_id,"expected_revision":0,"request_key":str(uuid.uuid4()),"reason":"Checked all group components"}
    assert patch(env,**confirm).status_code == 200
    assert patch(env,**confirm).status_code == 200
    assert BankTransaction.objects.filter(status="RECONCILED").count() == len(banks)
    lookup=env["client"].get(URL+"?target_id="+str(items[0].pk)).data
    assert lookup["count"] == len(banks)
    assert patch(env,action="group_clear",group_id=group_id,expected_revision=1,request_key=str(uuid.uuid4()),reason="Correct transfer grouping").status_code == 200
    assert not ReconciliationGroupTarget.objects.filter(active=True).exists()
    assert BankTransaction.objects.filter(status="UNMATCHED",reconciliation_group__isnull=True).count() == len(banks)
    history=env["client"].get(URL+"?history_for="+str(banks[0].pk)).data
    assert history["count"] == 3
    assert ReconciliationGroup.objects.get().evidence["bank_total"] == "100.00"


@pytest.mark.parametrize("fault",["total","reference","currency","account","duplicate","fees","missing_components","foreign"])
def test_group_validation_is_atomic(env,fault):
    row=bank(env);a=payment(env,"60");b=payment(env,"40")
    data=group_payload([row],[a,b])
    if fault == "total": Payment.objects.filter(pk=b.pk).update(amount=41)
    if fault == "reference": Payment.objects.filter(pk=b.pk).update(reference_number="OTHER-UTR")
    if fault == "currency": Payment.objects.filter(pk=b.pk).update(currency="USD")
    if fault == "account": Payment.objects.filter(pk=b.pk).update(source_account=None)
    if fault == "duplicate": data["targets"]=[data["targets"][0]]*2
    if fault == "fees": data["components"]["fees"]="1.00"
    if fault == "missing_components": del data["components"]
    if fault == "foreign":
        other=Tenant.objects.create(name="Foreign",workspace_key="foreign-recon")
        Payment.objects.filter(pk=b.pk).update(tenant=other)
    assert patch(env,**data).status_code in {400,404,409}
    assert not ReconciliationGroup.objects.exists() and not ReconciliationGroupTarget.objects.exists()
    row.refresh_from_db();assert row.status == "UNMATCHED"


def test_group_confirmation_revalidates_cancelled_target(env):
    row=bank(env);a=payment(env,"60");b=payment(env,"40")
    result=patch(env,**group_payload([row],[a,b]));assert result.status_code == 200
    from django.utils import timezone
    Payment.objects.filter(pk=b.pk).update(cancelled_at=timezone.now())
    assert patch(env,action="group_confirm",group_id=result.data["id"],expected_revision=0,reason="Confirm stale group",request_key=str(uuid.uuid4())).status_code == 404
    row.refresh_from_db();assert row.status == "MATCHED"


def test_server_pagination_filters_and_totals_reach_old_records(env):
    BankTransaction.objects.bulk_create([BankTransaction(tenant=env["tenant"],statement=env["statement"],transaction_date=date.today(),description="Transfer "+str(i),reference="OLD-REF" if i==0 else "",amount=-i-1,fingerprint=str(i)) for i in range(620)])
    data=env["client"].get(URL+"?page=7&page_size=100&sort=amount").data
    assert data["count"] == 620 and len(data["transactions"]) == 20 and data["counts"]["UNMATCHED"] == 620
    filtered=env["client"].get(URL+"?search=OLD-REF").data
    assert filtered["count"] == 1 and filtered["transactions"][0]["amount"] == "-1.00"
    for query in ["page=0","page_size=500","from=bad","from=2026-10-27&to=2026-10-26","sort=tenant","account_id=bad"]:
        assert env["client"].get(URL+"?"+query).status_code == 400


def test_finance_scope_and_auditor_read_only_history(env):
    row=bank(env);payment(env)
    env["member"].role="AUDITOR";env["member"].save()
    assert env["client"].get(URL+"?history_for="+str(row.pk)).status_code == 200
    assert env["client"].get(URL+"?suggestions_for="+str(row.pk)).status_code == 403
    assert patch(env,action="match",transaction_id=str(row.pk)).status_code == 403
    env["member"].role="FINANCE";env["member"].branch_scope_enabled=True;env["member"].save()
    assert env["client"].get(URL).status_code == 403


def test_group_preview_detects_changed_evidence_before_posting(env):
    row=bank(env);a=payment(env,"60");b=payment(env,"40")
    data=group_payload([row],[a,b]);preview=patch(env,**{**data,"action":"group_preview"})
    assert preview.status_code == 200 and not ReconciliationGroup.objects.exists()
    BankTransaction.objects.filter(pk=row.pk).update(description="Changed source narration")
    assert patch(env,**{**data,"expected_evidence_hash":preview.data["evidence_hash"]}).status_code == 409
    assert not ReconciliationGroup.objects.exists()


def test_payment_register_uses_full_filtered_count_and_exact_totals(env):
    from django.utils import timezone
    items=Payment.objects.bulk_create([Payment(tenant=env["tenant"],vendor=env["vendor"],amount="1.01",paid_at=date.today(),reference_number="OLDER-REF" if i==1 else str(i)) for i in range(320)])
    Payment.objects.filter(pk=items[0].pk).update(cancelled_at=timezone.now())
    data=env["client"].get("/api/v1/payments?paginated=1&page=4&page_size=100").data
    assert data["count"] == 319 and len(data["results"]) == 19 and data["total_recorded_amount"] == "322.19"
    filtered=env["client"].get("/api/v1/payments?paginated=1&search=OLDER-REF").data
    assert filtered["count"] == 1 and filtered["total_recorded_amount"] == "1.01"
    assert env["client"].get("/api/v1/payments?paginated=1&page_size=1000").status_code == 400
    env["member"].branch_scope_enabled=True;env["member"].save()
    assert env["client"].get("/api/v1/payments?paginated=1").status_code == 403


def test_driver_group_reversal_blocks_confirmation(env):
    from fleet.models import FleetDriver, DriverSalaryRecord, DriverSalaryPayment, DriverSalaryAdjustment
    driver=FleetDriver.objects.create(tenant=env["tenant"],name="Driver")
    salary=DriverSalaryRecord.objects.create(tenant=env["tenant"],driver=driver,period_start=date.today().replace(day=1),salary_amount=100,status="APPROVED")
    items=[DriverSalaryPayment.objects.create(tenant=env["tenant"],salary_record=salary,amount=amount,payment_reference="UTR-1234",source_account=env["account"],currency="INR") for amount in [60,40]]
    data=group_payload([bank(env)],items)
    for spec in data["targets"]:spec["target_type"]="DRIVER_SALARY_PAYMENT"
    result=patch(env,**data);assert result.status_code == 200,result.data
    DriverSalaryAdjustment.objects.create(tenant=env["tenant"],salary_record=salary,kind="PAYMENT_REVERSAL",amount=40,reason="Correcting recorded payment",original_payment=items[1],status="APPROVED")
    assert patch(env,action="group_confirm",group_id=result.data["id"],expected_revision=0,reason="Stale confirmation",request_key=str(uuid.uuid4())).status_code == 404


def test_group_customer_collections_preserve_credit_direction(env):
    from fleet.models import FleetCustomer, FleetVehicle, FleetDriver, FleetTrip, TransportOrder, TransportInvoice, TransportCollection
    tenant=env["tenant"]
    customer=FleetCustomer.objects.create(tenant=tenant,name="Customer")
    vehicle=FleetVehicle.objects.create(tenant=tenant,registration_number="MH01AB1234",normalized_registration="MH01AB1234")
    driver=FleetDriver.objects.create(tenant=tenant,name="Driver")
    trip=FleetTrip.objects.create(tenant=tenant,trip_number="TRIP-GROUP",vehicle=vehicle,driver=driver)
    order=TransportOrder.objects.create(tenant=tenant,order_number="ORDER-GROUP",customer=customer,origin="Pune",destination="Mumbai")
    invoice=TransportInvoice.objects.create(tenant=tenant,customer=customer,trip=trip,order=order,invoice_number="INV-GROUP",amount=100,status="ISSUED")
    items=[TransportCollection.objects.create(tenant=tenant,invoice=invoice,amount=amount,received_date=date.today(),reference="UTR-1234",source_account=env["account"],currency="INR") for amount in [60,40]]
    row=bank(env,"100")
    data=group_payload([row],items)
    for spec in data["targets"]:spec["target_type"]="CUSTOMER_COLLECTION"
    result=patch(env,**data);assert result.status_code == 200,result.data
    assert patch(env,action="group_confirm",group_id=result.data["id"],expected_revision=0,reason="Verified customer receipt",request_key=str(uuid.uuid4())).status_code == 200
    row.refresh_from_db();assert row.status == "RECONCILED"


def test_foreign_saved_evidence_group_and_history_cannot_be_read_or_used(env):
    row=bank(env);a=payment(env,"60");b=payment(env,"40")
    result=patch(env,**group_payload([row],[a,b]));assert result.status_code == 200
    other=Tenant.objects.create(name="Foreign",workspace_key="foreign-history")
    user=User.objects.create_user(username="other-reviewer",email="other@bank.test")
    Membership.objects.create(tenant=other,user=user,role="FINANCE")
    client=APIClient();client.force_authenticate(user)
    for suffix in ["?history_for="+str(row.pk),"?group_for="+result.data["id"],"?suggestions_for="+str(row.pk)]:
        assert client.get(URL+suffix).status_code == 404
    assert client.patch(URL,{"action":"group_clear","group_id":result.data["id"],"request_key":str(uuid.uuid4()),"expected_revision":0,"reason":"Unauthorized"},format="json").status_code == 404


def test_labeled_rule_evaluation(env):
    """Twelve hand-labeled synthetic cases; evaluates recommendations, never auto-confirmation."""
    from datetime import timedelta
    from django.utils import timezone
    results=[]
    for index in range(12):
        amount=str(1000+index)
        ref="" if index in {4,5} else "UTR-"+str(index).zfill(4)
        row=bank(env,amount="-"+amount,reference=ref)
        item=payment(env,amount=amount,reference=ref.lower().replace("-"," "))
        expected=str(item.pk) if index<8 else None
        if index in {6,7}:payment(env,amount=amount,reference=ref)
        if index==8:Payment.objects.filter(pk=item.pk).update(paid_at=date.today()+timedelta(days=30))
        if index==9:Payment.objects.filter(pk=item.pk).update(source_account=None)
        if index==10:Payment.objects.filter(pk=item.pk).update(currency="USD")
        if index==11:Payment.objects.filter(pk=item.pk).update(cancelled_at=timezone.now())
        data=env["client"].get(URL+"?suggestions_for="+str(row.pk)).data
        candidates=data["suggestions"]
        recommendation=candidates[0]["target_id"] if len(candidates)==1 and "EXACT_NORMALIZED_REFERENCE" in candidates[0]["reason_codes"] else None
        results.append((expected,recommendation,len(candidates)))
    tp=sum(expected is not None and predicted==expected for expected,predicted,_ in results)
    fp=sum(predicted is not None and predicted!=expected for expected,predicted,_ in results)
    fn=sum(expected is not None and predicted!=expected for expected,predicted,_ in results)
    metrics={"cases":12,"true_positive":tp,"false_positive":fp,"false_negative":fn,
        "precision":tp/(tp+fp),"recall":tp/(tp+fn),"false_match_rate":fp/(tp+fp),
        "unmatched_rate":sum(size==0 for _,_,size in results)/12,
        "manual_review_without_unique_exact_reference_rate":sum(predicted is None for _,predicted,_ in results)/12}
    assert (tp,fp,fn)==(4,0,4)
    assert metrics["unmatched_rate"] == 4/12
    assert metrics["precision"] == 1 and metrics["recall"] == 0.5
    assert metrics["manual_review_without_unique_exact_reference_rate"] == 8/12
    print("SYNTHETIC_RECONCILIATION_EVALUATION",metrics)


@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(connection.vendor != "postgresql",reason="Requires PostgreSQL locks")
def test_concurrent_group_and_single_claims_allow_only_one_owner(env):
    a=bank(env,"-60");b=bank(env,"-40");single=bank(env);item=payment(env)
    payloads=[group_payload([a,b],[item]),{"action":"match","transaction_id":str(single.pk),"payment_id":str(item.pk)}]
    barrier=Barrier(2)
    def run(i):
        close_old_connections()
        try:
            client=APIClient();client.force_authenticate(env["user"]);barrier.wait(timeout=15)
            return client.patch(URL,payloads[i],format="json").status_code
        finally: connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(run,range(2)))
    assert sorted(results) == [200,409]
