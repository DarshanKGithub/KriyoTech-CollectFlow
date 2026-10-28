# KriyoPay production-readiness test cases

**Purpose:** release gate and repeatable test plan for the production-readiness review. `AUTOMATED PASS` means the named local test passed; it does not imply a live provider, PostgreSQL 18 deployment, third-party email provider, accountant sign-off, or recovery drill passed.

## Current status

### Local acceptance run — 27 October 2026

- Backend SQLite suite: **226 passed, 9 skipped**. The skips include PostgreSQL-only checks; this is not a substitute for the isolated PostgreSQL release run below.
- Invoice intake/extraction → approval → payment workflow: passed with a stubbed extraction provider.
- Driver trip completion → approval → salary settlement: passed using separate Driver, Fleet, Approver and Finance users.
- Reconciliation role matrix: passed for Owner, Finance, Auditor, Approver, Purchase, Store, Fleet and Driver. Branch-scoped memberships fail closed for workspace workflows and see only their assigned branch list because business records do not yet have branch ownership fields.
- Test bank feed generation, duplicate retry, test-data labeling and daily digest role separation: passed.
- Frontend TypeScript check: passed.
- The full route-by-route tenant/role matrix, live bank/ERP provider round trips and production recovery drills remain open.

| Area | Status | Evidence / remaining work |
|---|---|---|
| Razorpay billing lifecycle | `AUTOMATED PASS (mocked gateway)` | Order creation, server-side captured verification, signed webhook, duplicate event, failed payment, non-captured rejection, and refund lifecycle cases. No real Checkout browser session or public webhook delivery was performed. |
| Tenant isolation and roles | `PARTIAL` | Existing invoice/branch/export isolation and role tests pass. There is not yet a request-by-request wrong-tenant matrix over every route and every role. Complete the matrix below before accepting a paying tenant. |
| Invoice email intake | `PARTIAL` | Token auth, message idempotency and a basic PDF intake are covered. No provider-managed forwarding address, sender reputation/spam filtering, provider retries, antivirus, broad attachment-format, or extraction failure test has been proven. |
| AI/manual invoice extraction | `PARTIAL` | Gemini extraction is wired and confidence is exposed as an uncalibrated model estimate in the review UI. Automated provider contract and manual fallback tests are present. A live Gemini request and full human-confirmation/role matrix remain unverified. |
| Tally CSV | `AUTOMATED PASS (internal fixtures)` | Balance and tenant-scoped mapping checks are covered. No real accountant chart-of-accounts import or Tally application validation. CSV remains the supported integration; XML posting is not validated. |
| Audit logs | `PARTIAL` | Tests cover selected upload, correction, approval, export, payment and admin events. No exhaustive action-to-event reconciliation or retention/immutability operations test exists. |
| Backup, restore, monitoring | `NOT VERIFIED / RELEASE BLOCKER` | No tested daily PostgreSQL backup/restore evidence, independent staging/production validation, centralized error monitoring, or job-failure alert drill was found in the repository. |

## Automated test commands

Run from `backend` in PowerShell:

```powershell
$env:DJANGO_TEST_SQLITE='1'
.\.venv\Scripts\pytest.exe -q
```

The current suite is configured to use SQLite for local automated runs. Before release, repeat the suite and migration checks against an isolated PostgreSQL 18 test database. The SQLite result does not validate PostgreSQL-specific behavior or production database configuration.

Run frontend tests from `frontend`:

```powershell
npm test -- --reporter=dot
```

## Detailed test cases

### 1. Razorpay test-mode end-to-end

| ID | Scenario / expected result | Automated coverage |
|---|---|---|
| RP-01 | Owner/finance requests an eligible plan; server creates matching Razorpay order and pending local payment. No activation yet. | `admin_console.tests.AdminConsoleTests.test_razorpay_checkout_order_verify_and_duplicate_webhook_lifecycle` (network mocked) |
| RP-02 | Checkout returns signature; backend verifies HMAC and fetches Razorpay payment. Only exact order, amount, currency and `captured` status activate subscription and issue one billing invoice. | Same test; existing `test_verified_payment_activates_subscription_and_creates_billing_invoice` |
| RP-03 | Frontend reports success, but provider status is `authorized`, pending, wrong order, wrong amount or wrong currency. Return conflict; subscription remains trial/onboarding and no billing invoice is issued. | `test_frontend_success_claim_without_captured_server_payment_never_activates` currently checks `authorized`; extend wrong amount/order/currency variants before release. |
| RP-04 | Signed `payment.captured` webhook processes and activates once. Same provider event delivered twice does not issue a second billing invoice or extend a period twice. | Lifecycle test and `test_captured_webhook_task_activates_only_once` |
| RP-05 | Invalid webhook signature is rejected; repeated valid event ID is enqueued only once. | `test_webhook_requires_signature_and_is_idempotently_queued` |
| RP-06 | `payment.failed` marks pending payment failed, records reason and leaves subscription inactive. | `test_payment_failed_webhook_marks_pending_payment_failed_without_activation` |
| RP-07 | Partial and full refund events update refund/payment state; full refund marks subscription past due. Duplicate refund notification is idempotent. | Existing partial/full refund tests; duplicate refund webhook needs explicit replay assertion. |
| RP-08 | Provider order expires / checkout is abandoned; payment does not activate and pending payment can be reconciled or retried safely. | Not proven. Current receiver has no explicit `order.expired` event; test provider-supported event/error lifecycle and document operational reconciliation. |
| RP-09 | Real provider test: test key → browser Checkout → public HTTPS webhook → verify signature → wait for Celery task → confirm subscription and billing invoice in DB/UI. Repeat failure and refund paths. | Not run: needs provider test transaction, publicly reachable HTTPS callback, configured webhook secret, running PostgreSQL/Redis/Celery and an operator to inspect Razorpay dashboard. |

### 2. Tenant isolation and role matrix

Create Company A and Company B with distinct users, invoices, vendors, usage, settings, memberships, audit rows, and exports. Authenticate only as Company A and set Company A's workspace selector. For every route in `backend/invoices/urls.py`, also try a Company B UUID/workspace key in path, query string, body, and object ID where applicable.

| ID | Checks | Expected result |
|---|---|---|
| TI-01 | A lists invoices, vendors, users, audit, usage, settings, exceptions, approvals, PO/GRN, payments, notifications, reports and email logs. | No Company B records or metadata are returned. |
| TI-02 | A requests B invoice detail/source, exception, vendor, GRN, approval, attachment, export and update/delete IDs. | 404/denial; no mutation or data leakage. |
| TI-03 | A supplies B tenant/workspace ID to create, invite, update settings, export, intake-token, API-key, integration, import, or bulk operations. | Server derives tenant from authenticated membership or denies. Never trust caller-supplied tenant ID. |
| TI-04 | Cross-tenant external API key, webhook, portal token, Google integration and inbound email credentials. | Credentials work only for the issuing tenant; revoked/expired credentials fail closed. |
| TI-05 | Test roles OWNER, FINANCE, PURCHASE, STORE, APPROVER and AUDITOR against read/create/update/delete, approval, match, payment, settings, export, user admin, and audit routes. | Only documented role actions succeed. Read-only auditor cannot mutate; AI cannot approve/pay. |
| TI-06 | Disabled membership, deleted workspace, revoked token, missing workspace selector, and user belonging to two workspaces. | No accidental fallback to another tenant; explicit workspace selection and active membership enforced. |

Existing automated evidence includes `invoices.tests` tenant-scoped invoice reads and auditor restrictions, `phase3.tests` branch scoping, and tenant-scoped Tally mappings/exports. This is not yet the exhaustive route/role matrix above.

### 3. Email invoice intake

| ID | Checks | Expected result |
|---|---|---|
| EI-01 | Send same provider/message ID twice with valid workspace token. | One ingestion record; second response identifies duplicate delivery; no duplicate invoice creation. |
| EI-02 | PDF, JPEG, PNG, HEIC, HEIF attachments; several attachments in one message. | Each allowed attachment is stored once, linked to a review-required invoice and audit event. |
| EI-03 | No attachment, unsupported executable/HTML, invalid MIME, file >25 MB, >20 attachments or aggregate >100 MB. | Graceful partial/quarantine response; no executable is stored or processed. |
| EI-04 | Missing/bad/rotated token, unknown workspace, disabled plan feature, spoofed sender, spam-like message and provider retry. | Reject or quarantine without leaking tenant data; legitimate retry is safe. Sender allowlist/spam/antivirus policy must be configured and validated. |
| EI-05 | Valid email with corrupt PDF/image or extraction provider outage. | Intake remains traceable; invoice is visibly queued/failed and can be manually entered/retried. |
| EI-06 | Configure real mailbox forwarding/ingress provider and deliver a real message to its dedicated address. | Provider signature/authentication, attachments, retries, quarantine and operational alerts verified in staging. |

Current endpoint is `POST /api/v1/email-ingestion/<workspace_key>` protected by a per-tenant intake token; a dedicated mailbox/provider forwarding route and anti-spam/antivirus assurance are not established by repository tests.

### 4. AI extraction fallback and human review

| ID | Checks | Expected result |
|---|---|---|
| AI-01 | Gemini extraction provider succeeds with fields and per-field confidence. | Store output, leave invoice `REVIEW_REQUIRED`, surface editable fields and uncalibrated confidence to reviewer. |
| AI-02 | Provider timeout, malformed response, unreadable file, worker unavailable. | `EXTRACTION_FAILED` or clear retry/manual-entry state; user can manually create/correct invoice. |
| AI-03 | Low/missing confidence, conflicting total/tax/date, extraction lines. | Flag uncertain values; human explicitly confirms/corrects before matching or approval. |
| AI-04 | AI review suggestion accepted/dismissed. | Records human decision only; does not approve invoice, initiate payment, or change approval state on its own. |
| AI-05 | Attempt extraction/approval action as unauthorized role. | Denied by server permissions. |

Existing tests cover provider error/manual fallback and AI review not changing payment/approval state. Confidence persistence exists in `ExtractionResult`, but invoice API/UI currently does not expose it; this is a product gap.

### 5. Tally-ready CSV

| ID | Checks | Expected result |
|---|---|---|
| TA-01 | Export invoice with taxable amount, GST split, TDS, credit/debit note and rounding. | Debit equals credit exactly; no missing or double-counted tax/withholding. |
| TA-02 | Workspace maps supplier, expense, input GST, TDS and payable ledgers. | Correct mappings used; unmapped accounts block or clearly flag export. |
| TA-03 | Repeat export, wrong tenant invoice IDs, auditor role, CSV escaping, Unicode, large dataset. | Stable/idempotent output policy, no tenant leak, safe quoting and correct permissions. |
| TA-04 | Accountant validates the CSV against customer's real Tally chart of accounts and imports in a test company. | Accountant signs off the ledger mapping and imported voucher totals before production. |

Internal fixtures validate balanced output and workspace mapping. No real chart-of-accounts or Tally import result is recorded. Keep CSV as the supported path until this is signed off; no direct XML posting is approved by this test plan.

### 6. Audit logs

For each action below, assert event actor (or system identity), tenant, object, timestamp, outcome, before/after where applicable, and redaction of secrets/PII:

- Invoice upload/email intake, extraction queued/completed/failed, corrections, matching, duplicate decisions, exception assignment/resolution/override.
- Approval submission, step creation, delegation, decision, rejection, auto-approval rule evaluation.
- CSV export/download, mapping create/update/delete, imports and bulk preview/commit.
- User invitation, role change, membership revoke, settings changes, API keys, integrations, webhook settings.
- Payment order, payment verification/capture/failure, refund request/result, plan/entitlement/usage changes.
- Admin login/denial, company onboard/deletion, super-admin creation/password update.

Automated tests cover representative actions, not all of the listed matrix. Add an audit assertion to each write API's test; verify append-only retention and export permissions.

### 7. Backups, recovery, environments and monitoring

| ID | Operational drill | Required evidence |
|---|---|---|
| OPS-01 | Automated daily PostgreSQL 18 backup, encrypted and stored separately from DB host/account. | Job schedule, successful timestamp, retention, encryption and alert on failure. |
| OPS-02 | Restore latest backup into isolated staging; verify migration, row counts, file/object storage references, auth and invoice/payment integrity. | Dated restore report, recovery time and recovery point measured. Repeat quarterly and after backup changes. |
| OPS-03 | Validate production and staging have separate DBs, secrets, storage buckets, OAuth callback URLs, Razorpay keys/webhooks and email accounts. | Environment inventory and access review; no production secrets in tests/logs. |
| OPS-04 | Trigger controlled API error and Celery task failure. | Error-monitoring event and actionable alert arrive; owner, runbook and retry/dead-letter behavior recorded. |
| OPS-05 | Test Redis/Celery outage, DB unavailable, storage unavailable, disk full and webhook queue failure. | User-facing request is safe, data is recoverable, alerts fire, and retries do not duplicate side effects. |

These are not verified by unit tests. Do not onboard a paying customer until OPS-01/02/04 evidence exists and environment isolation is confirmed.

## Release sign-off

Record date, environment, commit, PostgreSQL version, tester, passed/failed IDs, defects, restore drill reference, accountant approval, and Razorpay webhook event IDs. A passing local suite alone is not production-readiness approval.
