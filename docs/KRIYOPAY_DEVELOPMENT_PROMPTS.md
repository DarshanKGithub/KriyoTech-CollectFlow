# KriyoPay — corrected development prompts

Prepared: 25 October 2026.

Use one prompt at a time. The supporting inventory, source evidence and verification limitations are in docs/KRIYOPAY_PROMPT_COMPARISON.md. These prompts authorize future work only when you submit them as a task; this document does not claim the proposed features are already implemented.

## Prompt 0 — Corrected master prompt: inspect and plan

~~~text
Act as the architect and engineer for the existing KriyoPay repository. Audit the current implementation, compare it with the requested financial/AI capabilities and propose the next small implementation stage. Do not implement application changes in this task.

Use the actual stack: Next.js 14, React 18, TypeScript, MUI/MUI X, Django REST Framework, PostgreSQL, SimpleJWT, Celery and Redis. Verify installed versions from manifests. Do not replace the backend with FastAPI or build React Native without a separate requirement.

Read docs/KRIYOPAY_PROMPT_COMPARISON.md, then recheck its claims against current source and tests. Preserve accounts payable, procurement, invoice extraction, fleet/trips, driver settlements, bank reconciliation, ERP connectors, plans and administration.

Keep these financial domains distinct:
1. admin_console subscription billing: companies paying KriyoPay through Razorpay.
2. payments.Payment and PaymentAllocation: internally recorded supplier payments.
3. Fleet customer collections and driver salary payments.
Do not assume each company is a connected gateway merchant. An internal payment record is not verified bank settlement.

Classify features as implemented-and-verified, partial, implemented-but-unverified, missing or needs-investigation. Compare all twelve requested roadmap capabilities. Cite relevant source paths and test cases. Do not infer completeness from a screen, endpoint or model alone.

Run safe checks on isolated synthetic data. Never print secrets, transmit real client data to AI, trigger live financial operations or write to the normal application database. Separate SQLite passes, PostgreSQL-only skips, environment failures and genuine defects.

Create or update:
- docs/KRIYOPAY_CURRENT_STATE.md
- docs/KRIYOPAY_GAP_ANALYSIS.md
- docs/KRIYOPAY_IMPLEMENTATION_PLAN.md

Prioritize financial correctness and access controls before AI. For the next stage list affected files, services/models/migrations/APIs, dependencies, cost, acceptance tests, risks and exclusions. Present the plan for review and stop before major feature development.
~~~

## Prompt 1 — Fix foundation defects first

**Recommended next implementation task.**

~~~text
Implement a focused financial-reliability repair stage in KriyoPay's existing Django/PostgreSQL and Next.js/MUI codebase.

Read docs/KRIYOPAY_PROMPT_COMPARISON.md and verify R1–R5 before editing. Reuse existing services and UI patterns. Do not add AI features, replace working workflows or mix subscription billing with workspace supplier payments.

Repair:
1. Razorpay webhook publication/recovery: a broker failure must not leave a RECEIVED event permanently acknowledged but unprocessed. Support bounded retries, stale-job recovery and concurrent/repeated delivery. transaction.on_commit alone is not a durable publication guarantee.
2. Subscription refund request idempotency: persist a durable intent and request fingerprint/key, reserve refundable value under an appropriate payment lock and distinguish pending, processed, failed and unknown outcomes. Do not hold database locks during slow remote calls. On timeout after possible provider success, investigate the existing attempt instead of blindly submitting a second refund.
3. Financial totals: align dashboard aging, outstanding reports and payable checks around approved credit/debit notes and active allocations, excluding cancelled payments. Use exact decimals and preserve original financial history.
4. Bank candidate sorting: use stable target-type/target-ID tie-breakers across supplier/driver/collection candidates. Invalid UUIDs must return useful validation errors.
5. Concurrent bank matching: preserve uniqueness, revalidate target state at confirmation and return a safe 409 conflict rather than HTTP 500 when competing rows link the same target.

Use additive, backward-compatible migrations where needed. Preserve processed refunds and existing API contracts.

Add regression tests for enqueue failure/redelivery, duplicate webhook processing, concurrent refund reservations, ambiguous provider timeout, late/out-of-order refund events, approved note-adjusted balances, mixed-type candidate ties, invalid identifiers and concurrent matching. Use mocked provider transport and synthetic records; never call live payment/refund APIs.

Run locking tests on isolated PostgreSQL. If unavailable, clearly leave that acceptance gate open. Report exact changed files, migration commands, test results and unresolved limitations.
~~~

## Prompt 2 — Add financial source provenance and settlement import foundations

~~~text
Extend the existing KriyoPay financial models after foundation checks pass. Keep the Next.js/MUI frontend, Django/PostgreSQL backend and existing payment APIs.

First inspect bank imports, supplier payments, fleet collections/payments, subscription billing and ERP staging. Define explicit source account and currency for records that can be reconciled. Preserve original references, source IDs, source date/time semantics, file hashes and authorized source-file access.

Backfill legacy data conservatively. An INR display convention does not prove a historic row's source currency or bank account. Mark unresolved legacy records for review; do not invent account IDs or perform implicit FX conversion.

Before adding provider settlements, present the required product-scope decision:
- KriyoPay's own subscription gateway settlements, visible to authorized billing admins; or
- tenant merchant settlements using explicitly authorized merchant accounts and credentials.
Never use KriyoPay's global subscription credentials to fetch another company's merchant data.

Start with reviewed CSV/XLSX settlement/refund-report imports. Reuse existing parser limits, staging/review and Celery infrastructure. Propose settlement header/items, gross/fee/fee-tax/refund/adjustment/net fields, currency/account/provider identifiers and expected/actual dates. Unknown values remain unknown, not zero.

Implement import batches, source provenance, file/record idempotency, row-level errors, conflict review and auditable corrections/reversals. Do not silently overwrite verified financial facts. Leave live provider API ingestion disabled until account credentials and access policy are configured.

Acceptance: repeated imports do not duplicate facts; foreign tenant/account data is inaccessible; invalid or oversized input does not partially post; component arithmetic is verifiable; currencies cannot be silently mixed; original evidence remains accessible only to authorized users. Add migrations and isolated tests. No live gateway operations.
~~~

## Prompt 3 — Extend smart reconciliation and reviewer feedback

~~~text
Improve the existing KriyoPay BankReconciliation workflow; do not create a second matching application. Use Django services, PostgreSQL transactions and the current MUI reconciliation center.

Inspect phase3/views.py, phase3/models.py, payments/services.py and the completed foundation/provenance changes. Preserve supplier-payment, customer-collection and driver-salary-payment support.

Require authorized tenant/account, currency and debit/credit direction before generating candidates. Normalize narrations/references while preserving originals. Prefer exact stable identifiers, then explicit amount/date/reference rules. Add bounded fuzzy narration matching only when it improves a labeled evaluation set.

Persist reconciliation runs, candidate evidence, stable reason codes, rule/scorer version and explicit reviewer accept/reject decisions. Capture correction reasons. Repeated runs on unchanged data must not duplicate results; corrections must preserve history.

Multiple plausible candidates remain ambiguous. A heuristic ranking score is not a calibrated probability or fraud score. Keep explicit human confirmation for reconciliation; never auto-confirm just because a model reports high confidence.

Add one-to-many/many-to-one allocation support only where account/currency/provenance and component accounting exist. Group totals must reconcile exactly with explicit fees, taxes, refunds and adjustments. Bound search complexity. A coincidental sum is not sufficient evidence.

Add server-side pagination/filtering with total counts. Existing UI slices of 500 bank rows or 200 payments must not be used for all-record totals.

Test missing/varied references, competing equal-score candidates, duplicates, cross-tenant/account/currency access, retries, stale state, reversals, supported group matches and PostgreSQL races. Measure precision, recall, false-match, unmatched and manual-review rates with dataset size and labeling method. Do not claim production accuracy from synthetic fixtures.
~~~

## Prompt 4 — Build a read-only finance copilot

~~~text
Add a small read-only finance assistant to the existing KriyoPay Next.js/MUI and Django application. Reuse existing provider configuration where appropriate; the invoice-review suggestion screen is not already a general finance copilot.

Start with allowlisted query services for unmatched bank transactions, outstanding invoices, pending approvals, recorded payments and invoice discrepancies. Add settlement questions only when authorized settlement ingestion actually exists.

Enforce current tenant, account, applicable branch scope, role and feature entitlement server-side for every query. Use bounded ORM services, exact-decimal calculations, validated dates/currency, timeouts and row limits. Never accept raw SQL from a user or model.

An optional LLM may select permitted read tools and explain their returned evidence. Current balances must come from deterministic services, not vector search. Send minimum approved metadata externally only after explicit workspace enablement and external-processing confirmation. Provide a deterministic fallback when the model is unavailable.

Return scope, as-of timestamp, amounts/currency, authorized supporting record links and separate facts, calculations and hypotheses. Explicitly state missing history or unknown settlement dates. Do not manufacture records or financial conclusions.

Treat prompts, bank descriptions and documents as untrusted. Expose no tools for refunds, payments, approvals, editing verified records, sending messages or other side effects. Audit tool names, result scope and model/version metadata without retaining unnecessary raw sensitive prompts.

Use existing MUI patterns. Do not add a vector database for the initial release. Test prompt injection, cross-tenant/branch queries, forbidden tool access, decimal totals, incomplete records, stale data labeling, provider outage and evidence grounding against authoritative database results. Report costs and limitations.
~~~

## Prompt 5 — Extend financial documents and related-record investigation

~~~text
Extend KriyoPay's existing uploads, invoice extraction, bank/procurement imports, ERP staging and exception workflows. Do not rebuild them.

Select one unsupported financial document format based on actual customer samples. Define fields and validation before implementing. Reuse CSV/XLSX parsers for tables; prefer text-PDF extraction before OCR. Add OCR or LLM processing only when needed, configured and approved for the data involved. Keep manual correction.

Preserve source files/provenance under tenant/account access controls, safe retention and MIME/content validation. Bound file size, decompressed archive size, pages, rows and processing time. Never execute document instructions or macros. Sanitize user-controlled CSV exports against spreadsheet formula injection.

Validate identifiers, dates, currency and component arithmetic. Stage uncertainty for field-level human review instead of posting model guesses. Add retry-safe batches, duplicate protection and import summaries with row errors.

Use existing relational links for a bounded investigation view from invoice to PO/receipt/payment/bank row and, only where implemented, refund/settlement. Enforce permissions on every linked record. Do not introduce a graph database.

Allow evidence collection, discrepancy explanation drafts, report drafts and follow-up drafts through allowlisted services. Reuse human approval and notifications. Do not automatically send messages, change verified records or move money.

Add malformed-file, parser accuracy, injection, tenancy, duplicate/retry and correction-history tests. Document unsupported formats and sample coverage.
~~~

## Prompt 6 — Add explainable discrepancy rules; gate ML on data readiness

~~~text
Improve KriyoPay's financial investigations using the actual imported and reconciled records. Start with deterministic alerts rather than an unvalidated fraud model.

For each rule define source records, exact calculation, expected condition, reason code, severity and recommended next step. Reuse exceptions/notifications where appropriate; justify any new discrepancy-case model.

Cover supported duplicate debits, unmatched credits and arithmetic discrepancies. Add provider fee differences, missing reversals or settlement delays only after authoritative component data and expected dates exist. Missing imports are not proof of missing money.

Every alert needs tenant/account/currency, evidence references, timestamps, rule version, ownership and an audited acknowledge/resolve/reopen lifecycle. Do not accuse people of fraud or block payments on unvalidated scores.

Capture reviewed labels separately from model suggestions. Assess sample volume, completeness, label quality, account coverage, imbalance and time leakage before introducing ML. Evaluate a transparent baseline first with time-separated validation and compare any advanced model against it.

For each AI proposal record: problem, inputs, outputs/confidence semantics, baseline, evaluation set, metric, operating cost, failure modes, human review and implement/defer/reject decision. Forecasting and calibrated risk probabilities remain deferred when data is insufficient. Do not retrain automatically from every reviewer click.

Add rule/evidence/authorization tests. Publish evaluation results and limitations. No vector database, graph infrastructure or model-serving platform without a demonstrated need.
~~~

## Prompt 7 — Complete client-pilot readiness and measure performance

~~~text
Harden the existing KriyoPay stack for a controlled client pilot. Reuse current CI, configuration and operational conventions. Local precompiled next start is not an internet production deployment.

Verify and address:
- Tenant/branch/role/entitlement enforcement across reads, writes, exports and related-record references, including bank reconciliation.
- General authentication/API throttling and admin MFA enrollment, enforcement and recovery.
- Production secret validation, TLS/proxy-aware settings, secure cookies, CORS, safe errors and redacted logs; keep a separate usable localhost configuration.
- Durable protected document storage, retention and audit protection beyond model-level save/delete overrides.
- Supervised web/worker services, one beat scheduler, durable queue recovery and actionable monitoring.
- Scheduled outbound webhook delivery and permanently failed-job visibility.
- Safe PostgreSQL migrations, backups and an isolated restore drill.
- Reproducible dependency installation, dependency/security scans and triaged findings.
- CI with PostgreSQL concurrency tests, frontend checks and production build.

Measure representative cold/warm navigation and API latency using synthetic data. Record payload size, query counts and p50/p95 results against a reproducible baseline. Do not equate a successful build with faster clicks.

List acceptance gates and operational owners. Do not alter normal client records or call live financial APIs. Prepare deployment changes for review before exposing services or changing production access/security settings. Report completed, blocked and deferred work separately.
~~~

## Recommended sequence

Start with **Prompt 1**, then Prompt 2 and Prompt 3. Prompt 4 can initially answer questions over existing records after totals and access controls are reliable; it does not require fabricated settlement data. Use Prompts 5 and 6 for demonstrated customer needs. Prompt 7 is a parallel launch gate.

Do not run all prompts as one feature batch. Predictive settlement ML and dedicated graph infrastructure remain conditional on data quality, measurable value and evaluated performance.
