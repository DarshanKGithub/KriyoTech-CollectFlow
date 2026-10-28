# Prompt 1 — financial reliability repairs

Implemented: 26 October 2026 (Asia/Calcutta).

## Scope

This stage repairs R1–R5 from KRIYOPAY_PROMPT_COMPARISON.md. It does not add merchant settlement ingestion, multi-currency matching, AI or bank transfer initiation.

### Billing webhook recovery

- Signature-verified events retain their original payload. Reusing an event ID with a different payload returns 409.
- Publication has a durable five-minute lease, publication count and next-attempt timestamp. Broker failures preserve the event and schedule another attempt.
- Celery beat schedules admin_console.tasks.maintain_billing_webhooks every minute.
- Recovery handles old RECEIVED rows, failed publications and expired publication leases. Task row locks and processed-state checks make duplicate deliveries safe.
- Processing is bounded to six failed processing attempts; publication is bounded to twenty attempts. Exhausted events remain visible for investigation, not silently marked successful.
- Admin Payments displays publication count and next-attempt time.
- The worker processes the event in a transaction. A killed worker rolls back its changes; the expired publication lease makes it eligible for recovery.

Operator command, from backend:

~~~powershell
.\.venv\Scripts\python.exe manage.py recover_billing_webhooks
~~~

This command republishes due stored events. It does not call Razorpay itself; the worker may perform the existing read-only order verification while processing an order-paid event. It does not reset exhausted event counters. Investigate the source event and failure before any manual retry/reset.

### Durable subscription refund requests

- New RefundIntent records reserve refundable value while holding the subscription payment row lock.
- Existing PENDING/PROCESSED provider refunds and unlinked, non-failed intents count against refundable value. Linked intent/refund pairs are not counted twice.
- The reservation commits before provider submission. Slow provider calls do not hold the reservation lock.
- Only the first claim of a RESERVED intent may send a refund POST. Subsequent attempts use read-only provider lookup.
- An ambiguous result becomes UNKNOWN and retains its reservation. A missing result in the bounded provider lookup is not proof of failure and does not release funds.
- Provider receipt and notes carry the local intent reference. Read-only recovery checks up to ten pages of 100 refunds; a verified provider event can also resolve the intent.
- Confirmed processed refunds cannot be downgraded by late failed or pending events.
- Failed requests remain terminal for that intent. A genuinely new refund needs a new request key.
- An unlinked RESERVED intent left before submission retains its reservation; an authorized replay can claim and submit it once.
- Unlinked SUBMITTING intents are not queried immediately while the initial request can still be running; after two minutes, replay performs lookup only.
- The UI retains its request key in session storage after network or unknown outcomes. It sends exact paise as a string and reports unknown outcomes without claiming refund success.
- Admin Payments has a request-tracking table in addition to the existing provider-refund table.

Backward compatibility: callers that omit the request key get a deterministic key based on payment, requested amount and reason. Repeating that identical legacy request refers to the same intent. Integrations should supply explicit UUID keys so separate legitimate requests are distinguishable.

No live refund was sent during development. Existing processed refund records were not rewritten.

### API compatibility and additions

Existing endpoint:

~~~text
POST /api/v1/admin/payments/{payment_id}/refund
{
  "idempotency_key": "<UUID for this specific request>",
  "amount": "2001",
  "reason": "Approved correction"
}
~~~

Amount is a positive integer number of paise; omit it to reserve the remaining unreserved refundable balance. The same key with a changed amount or reason returns 409. Repeating the same key and payload checks the same intent.

Responses retain provider-refund fields when available and add intent_id, idempotency_key, status and message. A durable request with no verified provider refund returns 202. UNKNOWN/SUBMITTING is not a successful refund.

Read-only history:

~~~text
GET /api/v1/admin/payments/{payment_id}/refund
GET /api/v1/admin/refunds?intents=1
~~~

The first is restricted to super/billing admins. The second follows the existing refund-list admin role policy. They do not perform provider calls. Per-payment history is bounded to 100 rows; the global intent view is bounded to 200.

Provider lookup uses the payment-scoped refund listing and internal receipt/notes references described in the [official Razorpay SDK documentation](https://github.com/razorpay/razorpay-python/blob/master/documents/refund.md). The implementation does not assume that a receipt alone gives the provider an idempotency guarantee.

### Exact financial balances

payments.services.with_invoice_balances supplies SQL decimal annotations for approved notes, active allocations, net payable and outstanding balance.

~~~text
net payable = max(invoice total − approved credits + approved debits, 0)
outstanding = max(net payable − allocations on non-cancelled payments, 0)
~~~

Dashboard aging and aging/vendor-outstanding/payment-schedule reports now use this policy. The payment service's existing approval and amount checks remain in force. No invoice totals or historical payment amounts are altered.

### Bank reconciliation

- Candidate ties use target type and target ID, not nullable payment_id.
- Malformed bank-row/target UUIDs return 400.
- The bank row and target are locked; competing rows attempting the same target serialize.
- Target eligibility, tenant, signed direction and exact amount are checked again at confirmation.
- Cancelled supplier payments, unapproved salary records and salary payments with approved reversals are not eligible.
- Integrity conflicts return 409 through an inner savepoint.
- Already matched/reconciled rows require explicit unmatch before replacement.

## Additional confirmed defect repaired

The first full PostgreSQL run exposed a pre-existing WhatsApp recovery crash: FOR UPDATE on nullable related rows. WhatsApp message draft send/reconcile queries now lock only the draft row. The existing evidence and waiting-period requirements remain in force.

## Migration and rollout

Migration: admin_console.0005_razorpaywebhookevent_next_attempt_at_and_more.

It adds two recovery fields and the RefundIntent table. It is additive and was applied successfully to the local application database. No financial record data migration is included.

For another environment:

~~~powershell
.\.venv\Scripts\python.exe manage.py migrate admin_console 0005
~~~

Deploy the matching backend code and frontend together. Restart Django, Celery worker and the single beat scheduler so the new task registration/schedule is loaded. Existing worker processes do not hot-reload new Python code.

The UI/build was prepared; running services were not forcibly stopped or live financial actions triggered. Monitor UNKNOWN refunds and exhausted webhook events after deployment.

## Verification

- New test file: backend/admin_console/test_foundation.py.
- New UI tests: Frontend/src/app/admin-console/payments/page.test.tsx.
- Final complete suite in a uniquely named PostgreSQL test database: **177 passed**, including concurrency cases; no skips.
- Frontend: **18 tests passed across six files**.
- Frontend production build generated all 62 pages successfully; type/lint checks passed. The final copy-only refund helper-text change and new test file were followed by another type/lint check.
- Django check passed; migration drift check reported No changes detected.
- Earlier sandbox SQLite run: 168 passed, 7 PostgreSQL skips, one temporary-directory setup error. The final PostgreSQL run supersedes that incomplete result.
- Earlier full PostgreSQL run: 175 passed and one pre-existing WhatsApp failure, subsequently repaired. A targeted PostgreSQL rerun passed 19 cases before the final full suite.
- The first PostgreSQL runner setup replaced TEST defaults and failed with missing MIRROR; corrected before the successful runs. That harness error did not indicate an application defect.
- Initial sandbox PostgreSQL/build attempts were blocked by Windows permissions and rerun outside the sandbox.
- Test databases were separate from the application database. Synthetic files, in-memory Celery and mocked/blocked external HTTP were used. One earlier synthetic test database that could not clean up due to a test-thread connection was explicitly removed; test threads now close their connections.
- Git diff review was unavailable because this checkout is not a Git repository. Changed source files and generated migration operations were inspected directly.

## Remaining limits

- Live Razorpay delivery, worker/beat operational restart and provider acceptance have not been verified here.
- UNKNOWN refunds require verified lookup/webhook evidence or operator investigation; there is intentionally no automatic resubmission or blind reservation release.
- A provider account can have refunds beyond the bounded lookup window; unresolved outcomes remain UNKNOWN.
- Account/currency provenance, tenant merchant settlements, branch/feature enforcement gaps, production hardening and AI roadmap features belong to later stages.
- This is not a claim that the entire product has met production launch criteria.
