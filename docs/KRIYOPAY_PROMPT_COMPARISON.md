# KriyoPay — supplied AI roadmap versus existing implementation

Reviewed: 25 October 2026 (Asia/Calcutta).

Update, 26 October: R1–R5 have subsequently been addressed in the Prompt 1 implementation. See foundation-reliability.md for current behavior, tests and rollout limits. The tables below preserve the original audit snapshot.

## Correct the starting assumptions

The supplied prompt's audit-first approach, exact arithmetic, human review and tenant isolation requirements are useful. Its technology and business assumptions need correction:

- Actual frontend: **Next.js 14, React 18, TypeScript, MUI/MUI X**. No React Native app found.
- Actual backend: **Django 5, Django REST Framework, SimpleJWT, Celery and Redis**. No FastAPI app found.
- PostgreSQL is configured for normal operation; SQLite is an explicit test option.
- **Subscription billing:** admin_console.Payment represents companies paying KriyoPay through Razorpay.
- **Workspace accounting:** payments.Payment represents internally recorded supplier payments and invoice allocations. It does not initiate bank transfers.
- **Fleet accounting:** customer collections and driver salary payments are separate models.
- Existing Razorpay billing does **not** establish that each client has connected a merchant gateway account or that provider settlement reports are being ingested.
- Preserve procurement, fleet/trips, driver settlements, ERP connectors and administration. Extend this product rather than creating a second one.

Evidence: Frontend/package.json; backend/requirements.txt; backend/config/settings.py; backend/admin_console/billing.py; backend/payments/models.py; backend/fleet/models.py.

The latest request is comparison and new prompts. **No application features or migrations were changed for this review.**

## Existing feature inventory

“Verified” means supported by executed synthetic-data tests for the stated scope. It does not establish every edge case or live provider integration.

| Area | Status | Evidence and limitations |
| --- | --- | --- |
| Authentication/authorization | Implemented and verified for tested cases; partial overall | JWT rotation, tenant memberships, finance/approver/auditor/driver roles and internal admin roles. General branch isolation remains incomplete. accounts/permissions.py; accounts/models.py; accounts/tests.py. |
| Company/user/account administration | Implemented and verified for tested cases | Invitations, plans, entitlements and company checkout. No provider merchant/account registry for settlement reconciliation found. admin_console/views.py; admin_console/company_checkout.py. |
| Razorpay order initiation/verification | Implemented and verified for subscription scope | Server-created orders, signature checks and captured order/amount/currency validation. admin_console/billing.py; admin_console/views.py; admin_console/tests.py. |
| Webhook signature/replay handling | Implemented and verified in existing tests; recovery deficient | Persistent event IDs and Celery processing; queue-publication recovery gap described below. |
| Payment and transaction history | Implemented and verified for tested cases | Subscription payments, supplier allocations, transport collections and driver payments have separate records and semantics. |
| Refunds | Partially implemented | Subscription refund request and processed/failed webhook tests exist. Request idempotency/concurrency and ambiguous remote outcomes need work. No general workspace customer-refund ledger found. |
| Provider settlement ingestion | Missing | No merchant settlement header/items, settlement fee/tax ledger or provider-to-bank reconciliation found. Driver salary settlements are a different domain. |
| Bank ingestion | Implemented and verified for CSV/XLSX cases | Header mapping, hash-based imports, duplicate flags, row/size/archive limits and atomic validation. Account/currency provenance and retained original statement bytes are absent from BankStatement. phase3/views.py; phase3/models.py. |
| Invoice extraction | Implemented and verified with mocked providers | Gemini extraction, manual fallback, confidence review, task claims, retries and recovery. Hosted provider accuracy was not evaluated. vendors/services.py; invoices/tasks.py. |
| Procurement matching | Implemented and verified for tested cases | Invoice/PO/GRN tolerances, duplicate checks and blocking exceptions. Separate from bank matching. matching/services.py. |
| Bank reconciliation | Partially implemented | Ranked one-to-one suggestions, exact signed amount, dates, normalized reference/counterparty hints and manual confirmation. Supports supplier/collection/driver payment targets. No grouped settlement accounting. phase3/views.py:BankReconciliation. |
| Duplicate protection/idempotency | Partial across product | Payment keys, extraction claims, ERP constraints, file hashes and webhook IDs exist. Not a universal guarantee; refunds need more protection. |
| Discrepancy management | Partially implemented | Invoice exceptions, duplicate review and needs-attention inbox exist; no general settlement discrepancy case/component model found. |
| Reports and analytics | Implemented, with remaining correctness gaps | Aging, outstanding reports, due-date payment schedule and MUI dashboard. Existing “payment-forecast” is a due-date schedule, not ML. Balance policies need alignment. invoices/dashboard.py; invoices/phase2_extended.py. |
| Notifications/background jobs | Implemented for tested cases; operations unverified | Celery/beat extraction and ERP maintenance, reminders, notification preferences and webhook delivery command. Supervision and live external delivery not established. |
| Audit trail | Implemented and verified at tested model/API level | Actor/event metadata and model save/delete restrictions. Database-level tamper evidence not established. audit/models.py. |
| ERP and admin | Implemented with mocked/tested coverage; live acceptance unverified | Dynamics 365 Finance, ERPNext, Tally, Zoho Books and Inventory adapters; company/plan/payment administration. erp/catalog.py; erp/adapters.py; erp/tests.py. |
| AI/LLM | Partial against proposed roadmap | Gemini extraction plus OpenAI/Gemini invoice-review suggestions and accept/dismiss workflow. No general finance assistant, vector store or trained risk model found. |
| Deployment/testing | Partially implemented | CI, migrations and local startup exist. Deployment check warns; PostgreSQL concurrency, live integration, backup/restore and full production readiness remain separate gates. |

Backend paths in this table are relative to backend/.

## Comparison with all twelve requested capabilities

| # | Capability | Already present | Missing / next scope |
| --- | --- | --- | --- |
| 1 | Smart reconciliation | Deterministic bank candidates, reasons and manual review | Account/currency gating, persisted runs/candidates, ambiguity policy, group allocations, fee/refund/settlement components |
| 2 | ML anomaly/fraud detection | Duplicate checks, financial controls and invoice-review hints | Validated detector, alert lifecycle and evaluated labels; start with explainable rules |
| 3 | Finance copilot | Authorization, reports and invoice-review provider wrappers | Read-only query tools, evidence-backed answers, grounding and injection evaluations |
| 4 | Settlement/cash-flow prediction | Invoice due-date payment schedule | Settlement observations, expected/actual dates, historical data and evaluated baseline |
| 5 | Intelligent documents | Invoice extraction; bank/procurement CSV/XLSX parsing | Settlement/refund/remittance imports, text-PDF/OCR fallback and stronger source provenance |
| 6 | Graph intelligence | Relational invoice/PO/receipt/payment/bank links | Bounded related-record investigation view; no graph database justified yet |
| 7 | Feedback-driven matching | Match audit events and AI invoice-review decisions | Persisted rejected candidates, correction reasons, scorer versions and offline evaluation |
| 8 | Payment failure explanation | Stored subscription webhook events and failure details | Correlated event timeline, queue recovery visibility and evidence-based explanations |
| 9 | Settlement-delay detection | No provider settlement history found | Provider expectations, observed arrival dates, calendars and validated risk baseline |
| 10 | Controlled workflow agents | Reports, scheduled tasks and follow-up drafts | Allowlisted evidence/report-draft orchestration with approval gates |
| 11 | Revenue leakage intelligence | Invoice variances, duplicates, fleet profitability and unmatched rows | Provider gross/fee/tax/refund/reversal/net components and discrepancy accounting |
| 12 | Explainable risk scoring | Heuristic match scores/reasons and model-reported invoice confidence | Defined risk semantics, calibration, versions and evaluation; no fraud probabilities established |

## Findings to repair before major AI work

These are **source-code findings**, not newly reproduced production incidents.

| ID | Priority | Finding and evidence |
| --- | --- | --- |
| R1 | P0 | RazorpayWebhook saves RECEIVED before queue publication. If .delay() fails, it returns 503 but leaves RECEIVED; repeated delivery returns “already queued” without requeueing. Captured events can become stranded. backend/admin_console/views.py. |
| R2 | P0 | PaymentRefundCreate checks remaining refundable value without a payment lock, calls the provider, then inserts the local refund. No durable request intent/fingerprint fences concurrent attempts or success-followed-by-timeout. Gateway limits are not local idempotency. backend/admin_console/views.py. |
| R3 | P1 | Dashboard subtracts allocation sums from raw invoice totals; payment services adjust approved credit/debit notes and exclude cancelled payments. Dashboard/report/payment totals can disagree. backend/invoices/dashboard.py versus backend/payments/services.py. |
| R4 | P1 | Candidate sort uses score/date/payment_id; vendor candidates have a string payment_id and driver candidates None. Equal score/date can raise TypeError when comparing mixed types. backend/phase3/views.py:BankReconciliation.get. |
| R5 | P1 | Different bank rows can race to link one payment. Constraints prevent duplicate links, but the losing save lacks a clear IntegrityError-to-409 path. Revalidate target eligibility at confirmation. BankReconciliation.patch. |
| R6 | P1 | Bank statements/rows and supplier payments lack explicit source account/currency. Amount equality alone is insufficient for multi-account/currency matching. backend/phase3/models.py; backend/payments/models.py. |
| R7 | P1 | Branch scopes exist but are not generally applied to business queries. ERP explicitly excludes branch-scoped users. The entitlement route map gates payments but lacks bank-reconciliation. Define/test consistent access policy. backend/accounts/permissions.py; backend/erp/access.py. |
| R8 | P1 | Deployment checks returned five warnings. Admin MFA flow, production supervision, storage retention and backup/restore evidence remain gaps. Do not blindly enable HTTPS-only settings on localhost. |
| R9 | P2 | Bank lists cap at 500 rows, payments at 200 and candidate sets at 100 per type. Original bank file bytes are not retained by BankStatement. Avoid all-record conclusions from UI slices. |

## Verification performed

No live financial actions or normal application database writes were performed.

- Frontend: **16 tests passed in 5 files**, lint passed, TypeScript passed with incremental compilation disabled.
- Initial isolated backend run: **155 passed, 5 skipped, 4 failed and 1 error**. Five unsuccessful cases encountered Windows sandbox temporary-file/folder permissions.
- All **five affected cases passed on an escalated targeted rerun**. This was not a second full-suite run. Synthetic files, isolated SQLite, in-memory Celery, empty external credentials and blocked default external HTTP were used.
- Five PostgreSQL-specific cases remain unverified locally: four concurrent-payment scenarios and a fleet nullable-join regression. SQLite cannot establish row-lock correctness.
- Django configuration check passed. Migration drift check reported **No changes detected**. No migrations applied.
- Deployment warnings: **W004, W008, W012, W016 and W018**.
- No fresh production build, PostgreSQL suite, live provider acceptance, dependency vulnerability scan, financial-model accuracy evaluation or latency benchmark was run in this review. Earlier build results are not a fresh audit result.

## Recommendation

Use the focused prompts in KRIYOPAY_DEVELOPMENT_PROMPTS.md in this order:

1. Foundation repairs and regression tests.
2. Explicit source account/currency and a decision about merchant settlement scope.
3. Deterministic reconciliation and persisted review feedback.
4. Read-only finance copilot over supported records.
5. Document/investigation extensions and explainable discrepancy alerts.
6. ML only after data-readiness and evaluation gates.

Production hardening is a parallel client-launch gate. Do not attempt all twelve roadmap features in one implementation batch.
