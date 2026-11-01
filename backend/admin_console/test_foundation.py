import hashlib
import hmac
import json
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock, patch
import pytest
from django.db import connection, connections, close_old_connections
from django.utils import timezone
from rest_framework.test import APIClient
from accounts.models import User, Membership
from tenants.models import Tenant
from vendors.models import Vendor
from invoices.models import Invoice
from payments.models import Payment as SupplierPayment, PaymentAllocation, CreditDebitNote
from payments.services import with_invoice_balances, invoice_net_payable, allocated_total
from phase3.models import BankStatement, BankTransaction
from fleet.models import FleetDriver, DriverSalaryRecord, DriverSalaryPayment
from .models import Payment, PaymentRefund, RefundIntent, RazorpayWebhookEvent
from .billing import GatewayError
from .refunds import reserve, execute, observe, RefundConflict
from .webhook_recovery import publish_event, recover_events


@pytest.fixture
def records(db):
    tenant = Tenant.objects.create(name="Foundation", workspace_key="foundation")
    user = User.objects.create_user(username="foundation")
    Membership.objects.create(tenant=tenant, user=user, role="FINANCE")
    payment = Payment.objects.create(tenant=tenant, amount=10000, currency="INR",
                                    status="PAID", razorpay_payment_id="pay_foundation")
    return tenant, user, payment


@pytest.mark.django_db
def test_webhook_publication_failure_recovers_on_redelivery(settings):
    settings.RAZORPAY_WEBHOOK_SECRET = "synthetic-hook-secret"
    raw = json.dumps({"event": "payment.failed", "payload": {}}).encode()
    headers = {"HTTP_X_RAZORPAY_SIGNATURE": hmac.new(b"synthetic-hook-secret", raw, hashlib.sha256).hexdigest(),
               "HTTP_X_RAZORPAY_EVENT_ID": "foundation-event"}
    client = APIClient()
    with patch("admin_console.tasks.process_razorpay_webhook.delay", side_effect=RuntimeError("broker down")):
        assert client.generic("POST", "/api/v1/billing/razorpay/webhook", raw, content_type="application/json", **headers).status_code == 503
    event = RazorpayWebhookEvent.objects.get()
    assert event.status == "FAILED"
    RazorpayWebhookEvent.objects.update(next_attempt_at=timezone.now()-timedelta(seconds=1))
    with patch("admin_console.tasks.process_razorpay_webhook.delay") as queue:
        assert client.generic("POST", "/api/v1/billing/razorpay/webhook", raw, content_type="application/json", **headers).status_code == 202
        assert client.generic("POST", "/api/v1/billing/razorpay/webhook", raw, content_type="application/json", **headers).status_code == 200
        assert queue.call_count == 1


@pytest.mark.django_db
def test_webhook_recovery_is_bounded_and_republishes_expired_lease():
    due = RazorpayWebhookEvent.objects.create(event_id="due", event_type="payment.failed", payload={})
    RazorpayWebhookEvent.objects.create(event_id="done", event_type="payment.failed", status="PROCESSED")
    RazorpayWebhookEvent.objects.create(event_id="exhausted", event_type="payment.failed", attempt_count=6)
    with patch("admin_console.tasks.process_razorpay_webhook.delay") as queue:
        assert recover_events() == 1
        assert recover_events() == 0
        RazorpayWebhookEvent.objects.filter(pk=due.pk).update(next_attempt_at=timezone.now()-timedelta(minutes=1))
        assert recover_events() == 1
        assert queue.call_count == 2


def test_refund_reservation_replay_and_payload_conflict(records):
    _, user, payment = records
    key = uuid.uuid4()
    first = reserve(payment.pk, user, 6000, "Correction", key)
    assert reserve(payment.pk, user, 6000, "Correction", key).pk == first.pk
    with pytest.raises(RefundConflict):
        reserve(payment.pk, user, 5000, "Correction", key)
    with pytest.raises(RefundConflict):
        reserve(payment.pk, user, 5000, "Another intent", uuid.uuid4())
    assert RefundIntent.objects.count() == 1


def test_refund_timeout_never_reposts_and_recovers_by_reference(records):
    _, user, payment = records
    intent = reserve(payment.pk, user, 2000, "Correction", uuid.uuid4())
    gateway = Mock(side_effect=GatewayError("timeout"))
    assert execute(intent, gateway).status == "UNKNOWN"
    gateway.side_effect = None
    gateway.return_value = {"items": []}
    assert execute(intent, gateway).status == "UNKNOWN"
    assert [call.args[0] for call in gateway.call_args_list] == ["POST", "GET"]
    gateway.return_value = {"items": [{"id": "rfnd_recovered", "payment_id": payment.razorpay_payment_id,
        "amount": 2000, "currency": "INR", "status": "processed", "receipt": str(intent.pk)}]}
    # A provider receipt is also a supported correlation field.
    assert execute(intent, gateway).status == "PROCESSED"
    assert execute(intent, gateway).status == "PROCESSED"
    assert gateway.call_count == 3
    assert PaymentRefund.objects.count() == 1


def test_refund_stale_submit_is_read_only_and_webhook_wins(records):
    _, user, payment = records
    intent = reserve(payment.pk, user, 2000, "Correction", uuid.uuid4())
    RefundIntent.objects.filter(pk=intent.pk).update(status="SUBMITTING", attempted_at=timezone.now()-timedelta(minutes=3))
    gateway = Mock(return_value={"items": []})
    assert execute(intent, gateway).status == "UNKNOWN"
    assert gateway.call_args.args[0] == "GET"
    entity = {"id": "rfnd_webhook", "payment_id": payment.razorpay_payment_id, "amount": 2000,
              "notes": {"kriyopay_refund_intent": str(intent.pk)}}
    observe(entity, forced_status="PROCESSED")
    observe(entity, forced_status="FAILED")
    observe(entity, forced_status="PENDING")
    assert PaymentRefund.objects.get().status == "PROCESSED"
    assert RefundIntent.objects.get().status == "PROCESSED"
    payment.refresh_from_db()
    assert payment.status == "PARTIALLY_REFUNDED"


def test_malformed_provider_refund_keeps_reservation(records):
    _, user, payment = records
    intent = reserve(payment.pk, user, 2000, "Correction", uuid.uuid4())
    assert execute(intent, Mock(return_value={"id": "wrong", "amount": 3000})).status == "UNKNOWN"
    assert not PaymentRefund.objects.exists()
    with pytest.raises(RefundConflict):
        reserve(payment.pk, user, 9000, "Second refund", uuid.uuid4())


def test_refund_intent_history_is_admin_only_and_replay_is_read_only(records, settings):
    from .models import AdminStaff
    tenant, user, payment = records
    client = APIClient(); client.force_authenticate(user)
    url = f"/api/v1/admin/payments/{payment.pk}/refund"
    assert client.get(url).status_code == 403
    staff = AdminStaff.objects.create(user=user, role="BILLING_ADMIN")
    from .test_helpers import authenticate_staff
    authenticate_staff(client, staff)
    settings.RAZORPAY_KEY_ID = "synthetic"
    settings.RAZORPAY_KEY_SECRET = "synthetic"
    key = str(uuid.uuid4())
    data = {"amount": 2000, "reason": "Correction", "idempotency_key": key}
    with patch("admin_console.views.razorpay_request", side_effect=GatewayError("timeout")) as gateway:
        assert client.post(url, data, format="json").data["status"] == "UNKNOWN"
        assert client.post(url, data, format="json").data["status"] == "UNKNOWN"
        assert [call.args[0] for call in gateway.call_args_list] == ["POST", "GET"]
    history = client.get(url)
    assert history.status_code == 200
    assert history.data["intents"][0]["idempotency_key"] == key
    listing = client.get("/api/v1/admin/refunds?intents=1")
    assert listing.status_code == 200
    assert listing.data[0]["status"] == "UNKNOWN"


def test_balances_include_approved_notes_and_ignore_cancelled_payments(records):
    tenant, user, _ = records
    vendor = Vendor.objects.create(tenant=tenant, name="Supplier", approved=True)
    inv = Invoice.objects.create(tenant=tenant, vendor=vendor, invoice_total=100, status="PAYMENT_READY")
    for kind, amount in [("CREDIT", 10), ("DEBIT", 5)]:
        CreditDebitNote.objects.create(tenant=tenant, invoice=inv, kind=kind, note_number=kind,
                                      amount=amount, reason="OTHER", status="APPROVED")
    for amount, cancelled in [(20, False), (40, True)]:
        payment = SupplierPayment.objects.create(tenant=tenant, vendor=vendor, amount=amount,
            paid_at=timezone.localdate(), cancelled_at=timezone.now() if cancelled else None)
        PaymentAllocation.objects.create(tenant=tenant, invoice=inv, payment=payment, amount=amount)
    row = with_invoice_balances(Invoice.objects.filter(pk=inv.pk)).get()
    assert row.outstanding_balance == invoice_net_payable(inv)-allocated_total(inv) == Decimal("75")
    from invoices.dashboard import dashboard_analytics
    assert sum(Decimal(row["amount"]) for row in dashboard_analytics(tenant, include_finance=True)["payable_aging"]) == 75


def bank_fixture(tenant, user):
    from settlements.models import SourceAccount
    account = SourceAccount.objects.create(tenant=tenant, scope="TENANT", name="Bank", kind="BANK", provider="BANK", external_reference=uuid.uuid4().hex, currency="INR")
    vendor = Vendor.objects.create(tenant=tenant, name="Supplier", approved=True)
    payment = SupplierPayment.objects.create(tenant=tenant, vendor=vendor, source_account=account, currency="INR", amount=100, paid_at=timezone.localdate())
    statement = BankStatement.objects.create(tenant=tenant, source_account=account, currency="INR", filename="synthetic.csv", content_hash=uuid.uuid4().hex)
    txn = BankTransaction.objects.create(tenant=tenant, statement=statement, amount=-100,
        transaction_date=timezone.localdate(), description="Transfer", fingerprint=uuid.uuid4().hex)
    client = APIClient()
    client.force_authenticate(user)
    return client, payment, txn


def test_bank_mixed_candidates_ties_and_invalid_ids(records):
    tenant, user, _ = records
    client, payment, txn = bank_fixture(tenant, user)
    driver = FleetDriver.objects.create(tenant=tenant, name="Driver")
    salary = DriverSalaryRecord.objects.create(tenant=tenant, driver=driver,
        period_start=timezone.localdate().replace(day=1), salary_amount=100, status="APPROVED")
    DriverSalaryPayment.objects.create(tenant=tenant, salary_record=salary, source_account=txn.statement.source_account, currency="INR", amount=100)
    result = client.get(f"/api/v1/bank-reconciliation?suggestions_for={txn.pk}")
    assert result.status_code == 200
    assert {row["target_type"] for row in result.data["suggestions"]} == {"VENDOR_PAYMENT", "DRIVER_SALARY_PAYMENT"}
    for data in [{"transaction_id": "invalid", "action": "match"},
                 {"transaction_id": str(txn.pk), "action": "match", "payment_id": "invalid"}]:
        assert client.patch("/api/v1/bank-reconciliation", data, format="json").status_code == 400


def test_bank_confirmation_revalidates_cancelled_target(records):
    tenant, user, _ = records
    client, payment, txn = bank_fixture(tenant, user)
    url = "/api/v1/bank-reconciliation"
    assert client.patch(url, {"transaction_id": str(txn.pk), "action": "match",
                             "payment_id": str(payment.pk)}, format="json").status_code == 200
    SupplierPayment.objects.filter(pk=payment.pk).update(cancelled_at=timezone.now())
    assert client.patch(url, {"transaction_id": str(txn.pk), "action": "reconcile"}, format="json").status_code == 404
    txn.refresh_from_db()
    assert txn.status == "MATCHED"


@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(connection.vendor != "postgresql", reason="Requires PostgreSQL row locks")
@pytest.mark.parametrize("kind", ["refund", "bank"])
def test_concurrent_reservations_and_bank_links(kind):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    tenant = Tenant.objects.create(name="Concurrent", workspace_key="concurrent")
    user = User.objects.create_user(username="concurrent")
    Membership.objects.create(tenant=tenant, user=user, role="FINANCE")
    payment = Payment.objects.create(tenant=tenant, amount=10000, status="PAID", razorpay_payment_id="pay_concurrent")
    _, target, first = bank_fixture(tenant, user)
    second = BankTransaction.objects.create(tenant=tenant, statement=first.statement, amount=-100,
        transaction_date=timezone.localdate(), description="Other", fingerprint=uuid.uuid4().hex)
    gate = Barrier(2)
    def run(index):
        close_old_connections()
        try:
            gate.wait(timeout=15)
            if kind == "refund":
                try:
                    reserve(payment.pk, user, 6000, "Concurrent request", uuid.uuid4())
                    return 201
                except RefundConflict:
                    return 409
            client = APIClient(); client.force_authenticate(user)
            return client.patch("/api/v1/bank-reconciliation", {"transaction_id": str([first, second][index].pk),
                "action": "match", "payment_id": str(target.pk)}, format="json").status_code
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, [0, 1]))
    assert sorted(results) == ([201, 409] if kind == "refund" else [200, 409])
