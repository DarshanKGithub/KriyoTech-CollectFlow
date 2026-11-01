import io
import uuid
from datetime import date
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection, connections, close_old_connections, transaction, IntegrityError
from rest_framework.test import APIClient
from accounts.models import User, Membership
from admin_console.models import AdminStaff, Payment as BillingPayment
from audit.models import AuditLog
from tenants.models import Tenant
from vendors.models import Vendor
from payments.models import Payment
from phase3.models import BankStatement, BankTransaction
from .models import SourceAccount, ImportBatch, SettlementRecord


@pytest.fixture
def env(db, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "public"
    settings.FINANCIAL_SOURCE_ROOT = tmp_path / "private"
    tenant = Tenant.objects.create(name="Client", workspace_key="settlement-client")
    other = Tenant.objects.create(name="Other", workspace_key="settlement-other")
    user = User.objects.create_user(username="settlement-finance", email="settlement-finance@example.test")
    member = Membership.objects.create(tenant=tenant, user=user, role="FINANCE")
    staff = User.objects.create_user(username="settlement-billing", email="settlement-billing@example.test")
    staff_profile = AdminStaff.objects.create(user=staff, role="BILLING_ADMIN")
    client = APIClient(); client.force_authenticate(user)
    admin = APIClient()
    from admin_console.test_helpers import authenticate_staff
    authenticate_staff(admin, staff_profile)
    merchant = SourceAccount.objects.create(scope="TENANT", tenant=tenant, name="Client gateway", kind="GATEWAY",
        provider="RAZORPAY", external_reference="acc_client", currency="INR")
    bank = SourceAccount.objects.create(scope="TENANT", tenant=tenant, name="Client bank", kind="BANK",
        provider="BANK", external_reference="bank-1234", currency="INR")
    platform = SourceAccount.objects.create(scope="PLATFORM", name="Platform gateway", kind="GATEWAY",
        provider="RAZORPAY", external_reference="acc_platform", currency="INR")
    return locals()


def csv_bytes(rows=None):
    return (rows or "record_type,external_id,currency,gross,fees,fee_tax,refunds,adjustments,net\nSETTLEMENT,setl_1,INR,100,2,1,0,0,97\n").encode()


def upload(client, account, raw=None, prefix="/api/v1/settlements", name="source.csv"):
    return client.post(prefix+"/imports", {"account_id": str(account.pk),
        "file": SimpleUploadedFile(name, raw or csv_bytes(), content_type="text/csv")}, format="multipart")


def decide(client, batch_id, prefix="/api/v1/settlements", **extra):
    return client.post(prefix+"/imports/"+str(batch_id), {"decision": "APPROVED", "note": "Checked source account and report", **extra}, format="json")


def test_platform_and_tenant_scopes_cannot_be_mixed(env):
    s = env
    assert s["client"].get("/api/v1/admin/settlements/accounts").status_code == 403
    assert s["admin"].get("/api/v1/settlements/accounts").status_code == 403
    data = s["client"].get("/api/v1/settlements/accounts").data
    assert {item["id"] for item in data["accounts"]} == {str(s["merchant"].pk), str(s["bank"].pk)}
    assert {item["id"] for item in s["admin"].get("/api/v1/admin/settlements/accounts").data["accounts"]} == {str(s["platform"].pk)}
    assert upload(s["client"], s["platform"]).status_code == 404
    assert upload(s["admin"], s["merchant"], prefix="/api/v1/admin/settlements").status_code == 404
    foreign = SourceAccount.objects.create(scope="TENANT", tenant=s["other"], name="Foreign", kind="GATEWAY",
        provider="OTHER", external_reference="other", currency="INR")
    assert upload(s["client"], foreign).status_code == 404


def test_database_ownership_constraint_and_payload_ownership_rejected(env):
    with pytest.raises(IntegrityError), transaction.atomic():
        SourceAccount.objects.create(scope="PLATFORM", tenant=env["tenant"], name="Invalid",
            kind="BANK", provider="BANK", external_reference="bad", currency="INR")
    result = env["client"].post("/api/v1/settlements/accounts", {"name":"Bad","scope":"PLATFORM",
        "kind":"BANK","provider":"BANK","external_reference":"x","currency":"INR"}, format="json")
    assert result.status_code == 400


@pytest.mark.parametrize("platform", [False, True])
def test_staged_approval_idempotency_and_protected_original(env, platform):
    client = env["admin"] if platform else env["client"]
    account = env["platform"] if platform else env["merchant"]
    prefix = "/api/v1/admin/settlements" if platform else "/api/v1/settlements"
    first = upload(client, account, prefix=prefix)
    assert first.status_code == 201, first.data
    assert not SettlementRecord.objects.exists()
    assert upload(client, account, prefix=prefix).data["duplicate_import"]
    batch = ImportBatch.objects.get(pk=first.data["id"])
    with pytest.raises(ValueError):
        _ = batch.original_file.url
    assert str(env["settings"].MEDIA_ROOT) not in batch.original_file.path
    with batch.original_file.open("rb") as original:
        assert original.read() == csv_bytes()
    assert decide(client, batch.pk, prefix).status_code == 200
    assert decide(client, batch.pk, prefix).status_code == 200
    assert SettlementRecord.objects.count() == 1
    row = SettlementRecord.objects.get()
    assert row.net == Decimal("97.00")
    assert row.source_row.batch_id == batch.pk
    records = client.get(prefix+"/records").data
    assert records["results"][0]["net"] == "97.00"
    source = client.get(prefix+"/imports/"+str(batch.pk)+"/source")
    assert source.status_code == 200
    assert b"".join(source.streaming_content) == csv_bytes()
    outsider = env["client"] if platform else env["admin"]
    assert outsider.get(prefix+"/imports/"+str(batch.pk)+"/source").status_code == 403
    assert not BillingPayment.objects.exists()  # Import never activates billing or sends a payment.


def test_foreign_tenant_batch_rows_and_original_are_not_accessible(env):
    first = upload(env["client"], env["merchant"])
    outsider = User.objects.create_user(username="outsider", email="outsider@example.test")
    Membership.objects.create(tenant=env["other"], user=outsider, role="FINANCE")
    client = APIClient(); client.force_authenticate(outsider)
    for suffix in ("", "?rows=1", "/source"):
        assert client.get("/api/v1/settlements/imports/"+first.data["id"]+suffix).status_code == 404
    assert client.get("/api/v1/settlements/records").data["count"] == 0
    assert client.get("/api/v1/settlements/imports?account_id=not-a-uuid").status_code == 400


@pytest.mark.parametrize("change", ["currency", "arithmetic", "nonfinite", "precision", "duplicate"])
def test_invalid_rows_are_staged_but_never_approved(env, change):
    raw = csv_bytes().decode()
    if change == "currency": raw = raw.replace("setl_1,INR", "setl_1,USD")
    elif change == "arithmetic": raw = raw.replace(",97\n", ",98\n")
    elif change == "nonfinite": raw = raw.replace(",100,", ",NaN,")
    elif change == "precision": raw = raw.replace(",100,", ",100.001,")
    else: raw += raw.splitlines()[1]+"\n"
    result = upload(env["client"], env["merchant"], raw.encode())
    assert result.status_code == 201, result.data
    assert result.data["status"] == "INVALID"
    assert result.data["errors"]
    assert decide(env["client"], result.data["id"]).status_code == 400
    assert not SettlementRecord.objects.exists()


def test_unknown_components_are_not_imputed_and_require_acknowledgement(env):
    raw = b"record_type,external_id,currency,net\nSETTLEMENT,incomplete,INR,90\n"
    result = upload(env["client"], env["merchant"], raw)
    assert result.data["warnings"]
    assert decide(env["client"], result.data["id"]).status_code == 400
    assert decide(env["client"], result.data["id"], acknowledge_warnings=True).status_code == 200
    row = SettlementRecord.objects.get()
    assert row.gross is None and row.fees is None and row.adjustments is None
    assert row.net == Decimal("90")


def test_conflicting_ids_do_not_overwrite_and_full_reversals_preserve_history(env):
    first = upload(env["client"], env["merchant"])
    assert decide(env["client"], first.data["id"]).status_code == 200
    conflict = upload(env["client"], env["merchant"], csv_bytes().replace(b",100,2,1,0,0,97", b",200,2,1,0,0,197"))
    assert conflict.data["status"] == "INVALID"
    reverse = upload(env["client"], env["merchant"], b"record_type,external_id,currency,amount,reverses_type,reverses_id\nREVERSAL,rev_1,INR,97,SETTLEMENT,setl_1\n")
    assert decide(env["client"], reverse.data["id"]).status_code == 200
    assert SettlementRecord.objects.count() == 2
    original = SettlementRecord.objects.get(record_type="SETTLEMENT")
    assert original.net == Decimal("97")
    assert SettlementRecord.objects.get(record_type="REVERSAL").reverses_id == original.pk
    with pytest.raises(ValueError):
        original.save()


def test_approval_rechecks_conflict_after_concurrent_staging(env):
    first = upload(env["client"], env["merchant"])
    second = upload(env["client"], env["merchant"], csv_bytes().replace(b",100,2,1,0,0,97", b",200,2,1,0,0,197"))
    assert decide(env["client"], first.data["id"]).status_code == 200
    assert decide(env["client"], second.data["id"]).status_code == 400
    assert SettlementRecord.objects.count() == 1


def test_refund_report_does_not_initiate_a_refund_or_change_balances(env):
    result = upload(env["client"], env["merchant"], b"record_type,external_id,currency,amount,payment_reference\nREFUND,rfnd_source,INR,10,pay_source\n")
    assert decide(env["client"], result.data["id"]).status_code == 200
    assert SettlementRecord.objects.get().amount == Decimal("10")
    assert not BillingPayment.objects.exists() and not Payment.objects.exists()


@pytest.mark.parametrize("role,branch", [("AUDITOR", False), ("PURCHASE", False), ("FINANCE", True)])
def test_read_only_and_branch_scoped_access(env, role, branch):
    member = env["member"];member.role=role;member.branch_scope_enabled=branch;member.save()
    client = env["client"]
    assert upload(client, env["merchant"]).status_code == 403
    assert client.get("/api/v1/settlements/accounts").status_code == (200 if role == "AUDITOR" else 403)


def test_values_only_xlsx_and_original_retention(env):
    from openpyxl import Workbook
    workbook = Workbook();sheet=workbook.active
    sheet.append(["record_type","external_id","currency","net"])
    sheet.append(["SETTLEMENT","xlsx_1","INR",100])
    data = io.BytesIO();workbook.save(data);workbook.close()
    result = upload(env["client"], env["merchant"], data.getvalue(), name="source.xlsx")
    assert result.status_code == 201, result.data
    assert result.data["status"] == "NEEDS_REVIEW"
    bad = Workbook();bad.active.append(["record_type","external_id","currency","net"]);bad.active.append(["SETTLEMENT","formula","INR","=1+2"])
    data = io.BytesIO();bad.save(data);bad.close()
    assert upload(env["client"], env["merchant"], data.getvalue(), name="formula.xlsx").status_code == 400


def test_invalid_and_oversized_files_do_not_create_batches(env):
    client=env["client"];merchant=env["merchant"]
    for raw,name in [(b"bad","bad.xlsx"),(b"x","bad.pdf"),(b"x"*(10*1024*1024+1),"huge.csv")]:
        assert upload(client,merchant,raw,name=name).status_code == 400
    assert not ImportBatch.objects.exists()


def test_legacy_provenance_is_unknown_until_reviewed_and_blocks_cross_account_matching(env):
    s=env;tenant=s["tenant"];bank=s["bank"];client=s["client"]
    vendor=Vendor.objects.create(tenant=tenant,name="Supplier",approved=True)
    payment=Payment.objects.create(tenant=tenant,vendor=vendor,amount=100,paid_at=date.today())
    statement=BankStatement.objects.create(tenant=tenant,filename="legacy.csv",content_hash="legacy")
    txn=BankTransaction.objects.create(tenant=tenant,statement=statement,amount=-100,transaction_date=date.today(),description="Payment",fingerprint="legacy")
    assert payment.currency == "" and statement.source_account_id is None
    assert client.get("/api/v1/bank-reconciliation?suggestions_for="+str(txn.pk)).data["provenance_required"]
    data={"transaction_id":str(txn.pk),"action":"match","payment_id":str(payment.pk)}
    assert client.patch("/api/v1/bank-reconciliation",data,format="json").status_code == 409
    for kind,item in [("BANK_STATEMENT",statement),("VENDOR_PAYMENT",payment)]:
        result=client.post("/api/v1/settlements/provenance",{"record_type":kind,"record_id":str(item.pk),"account_id":str(bank.pk),"evidence":"Verified bank reference from synthetic source"},format="json")
        assert result.status_code == 200,result.data
    assert client.patch("/api/v1/bank-reconciliation",data,format="json").status_code == 200
    assert AuditLog.objects.filter(action="SOURCE_PROVENANCE_VERIFIED").count() == 2
    foreignbank=SourceAccount.objects.create(scope="TENANT",tenant=s["other"],name="Foreign bank",kind="BANK",provider="BANK",external_reference="foreign",currency="INR")
    assert client.post("/api/v1/settlements/provenance",{"record_type":"VENDOR_PAYMENT","record_id":str(payment.pk),"account_id":str(foreignbank.pk),"evidence":"Wrong"},format="json").status_code == 404


def test_bank_upload_can_retain_known_source_and_currency(env):
    client=env["client"];bank=env["bank"]
    raw=b"date,description,amount,reference\n2026-10-26,Receipt,100,UTR\n"
    result=client.post("/api/v1/bank-reconciliation",{"account_id":str(bank.pk),"file":SimpleUploadedFile("bank.csv",raw)},format="multipart")
    assert result.status_code == 201,result.data
    statement=BankStatement.objects.get()
    assert statement.source_account_id == bank.pk and statement.currency == "INR"
    with statement.original_file.open("rb") as original:
        assert original.read() == raw
    download=client.get("/api/v1/bank-reconciliation?source_for="+str(statement.pk))
    assert download.status_code == 200 and b"".join(download.streaming_content) == raw
    outsider=User.objects.create_user(username="bank-outsider",email="bank-outsider@example.test")
    Membership.objects.create(user=outsider,tenant=env["other"],role="FINANCE")
    foreign=APIClient();foreign.force_authenticate(outsider)
    assert foreign.get("/api/v1/bank-reconciliation?source_for="+str(statement.pk)).status_code == 404


def test_spreadsheet_identifier_numbers_are_not_silently_rounded(env):
    from openpyxl import Workbook
    book=Workbook();book.active.append(["record_type","external_id","currency","net"])
    book.active.append(["SETTLEMENT",1234567890123456,"INR",100])
    raw=io.BytesIO();book.save(raw);book.close()
    result=upload(env["client"],env["merchant"],raw.getvalue(),name="numeric-id.xlsx")
    assert result.data["status"] == "INVALID"
    assert "text cell" in result.data["errors"][0]["message"]


@pytest.mark.parametrize("amount", ["1.001", "10000000000000000", "NaN", "Infinity"])
def test_bank_sources_reject_unrepresentable_money_without_partial_rows(env, amount):
    raw=("date,description,amount\n2026-10-26,Invalid,"+amount+"\n").encode()
    result=env["client"].post("/api/v1/bank-reconciliation",{"account_id":str(env["bank"].pk),"file":SimpleUploadedFile("bad.csv",raw)},format="multipart")
    assert result.status_code == 400
    assert not BankStatement.objects.exists() and not BankTransaction.objects.exists()


def test_bank_duplicate_rows_are_compared_within_their_source_account(env):
    client=env["client"]
    first=b"date,description,amount\n2026-10-26,Receipt,100\n"
    second=first+b"2026-10-26,Another receipt,200\n"
    other=SourceAccount.objects.create(scope="TENANT",tenant=env["tenant"],name="Other bank",kind="BANK",provider="BANK",external_reference="bank2",currency="INR")
    for bank,raw in [(env["bank"],first),(other,second)]:
        result=client.post("/api/v1/bank-reconciliation",{"account_id":str(bank.pk),"file":SimpleUploadedFile("bank.csv",raw)},format="multipart")
        assert result.status_code == 201
    assert BankTransaction.objects.filter(status="UNMATCHED").count() == 3


def test_missing_gateway_credentials_never_fall_back_to_platform(env, settings):
    settings.RAZORPAY_KEY_ID="platform-key-not-to-be-used"
    settings.RAZORPAY_KEY_SECRET="platform-secret-not-to-be-used"
    from unittest.mock import patch
    with patch("admin_console.billing.razorpay_request",side_effect=AssertionError("Live gateway must not be called")):
        assert upload(env["client"],env["merchant"]).status_code == 201
        assert env["client"].post("/api/v1/settlements/accounts",{"name":"Unsafe","kind":"GATEWAY","provider":"RAZORPAY","external_reference":"unsafe","currency":"INR","api_key":"unaccepted"},format="json").status_code == 400
        assert env["client"].get("/api/v1/settlements/accounts").data["accounts"][0]["live_sync_enabled"] is False


def test_disabled_accounts_conflicting_provenance_and_missing_files(env):
    client=env["client"];account=env["merchant"]
    result=upload(client,account)
    assert client.patch("/api/v1/settlements/accounts/"+str(account.pk),{"active":False},format="json").status_code == 200
    assert decide(client,result.data["id"]).status_code == 400
    assert upload(client,account).status_code == 404
    assert client.patch("/api/v1/settlements/accounts/"+str(account.pk),{"currency":"USD"},format="json").status_code == 400
    batch=ImportBatch.objects.get(pk=result.data["id"]);batch.original_file.delete(save=False)
    assert client.get("/api/v1/settlements/imports/"+str(batch.pk)+"/source").status_code == 404
    second=SourceAccount.objects.create(scope="TENANT",tenant=env["tenant"],name="Other bank",kind="BANK",provider="BANK",external_reference="bank2",currency="INR")
    statement=BankStatement.objects.create(tenant=env["tenant"],filename="verified.csv",content_hash="verified",source_account=env["bank"],currency="INR")
    assert client.post("/api/v1/settlements/provenance",{"record_type":"BANK_STATEMENT","record_id":str(statement.pk),"account_id":str(second.pk),"evidence":"Overwriting is not allowed"},format="json").status_code == 409


def test_malformed_json_shapes_are_validation_errors(env):
    client=env["client"]
    assert client.post("/api/v1/settlements/accounts",[{"name":"bad"}],format="json").status_code == 400
    assert client.post("/api/v1/settlements/provenance",{"record_type":[]},format="json").status_code == 400
    batch=upload(client,env["merchant"])
    assert client.post("/api/v1/settlements/imports/"+batch.data["id"],{"decision":[],"note":"Bad shape"},format="json").status_code == 400


def test_matching_rejects_different_accounts_currencies_and_disabled_accounts(env):
    bank=env["bank"];tenant=env["tenant"];client=env["client"]
    other=SourceAccount.objects.create(scope="TENANT",tenant=tenant,name="Second bank",kind="BANK",provider="BANK",external_reference="bank2",currency="INR")
    vendor=Vendor.objects.create(tenant=tenant,name="Supplier",approved=True)
    payment=Payment.objects.create(tenant=tenant,vendor=vendor,amount=100,paid_at=date.today(),source_account=other,currency="INR")
    statement=BankStatement.objects.create(tenant=tenant,filename="source.csv",content_hash="source",source_account=bank,currency="INR")
    txn=BankTransaction.objects.create(tenant=tenant,statement=statement,amount=-100,transaction_date=date.today(),description="Transfer",fingerprint="source")
    data={"transaction_id":str(txn.pk),"action":"match","payment_id":str(payment.pk)}
    assert not client.get("/api/v1/bank-reconciliation?suggestions_for="+str(txn.pk)).data["suggestions"]
    assert client.patch("/api/v1/bank-reconciliation",data,format="json").status_code == 409
    Payment.objects.filter(pk=payment.pk).update(source_account=bank,currency="USD")
    assert client.patch("/api/v1/bank-reconciliation",data,format="json").status_code == 409
    Payment.objects.filter(pk=payment.pk).update(currency="INR")
    SourceAccount.objects.filter(pk=bank.pk).update(active=False)
    assert client.patch("/api/v1/bank-reconciliation",data,format="json").status_code == 409


@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(connection.vendor != "postgresql", reason="Requires PostgreSQL row locks")
def test_concurrent_file_import_and_approval_are_idempotent(env):
    def race(action):
        barrier=Barrier(2)
        def run(_):
            close_old_connections()
            try:
                client=APIClient();client.force_authenticate(env["user"])
                barrier.wait(timeout=15)
                return action(client)
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(run,range(2)))
    assert sorted(race(lambda client:upload(client,env["merchant"]).status_code)) == [200,201]
    batch=ImportBatch.objects.get()
    assert race(lambda client:decide(client,batch.pk).status_code) == [200,200]
    assert SettlementRecord.objects.count() == 1

