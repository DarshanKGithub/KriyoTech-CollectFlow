# Test Plan

## Current verification status (2026-10-18)

- Django system check: passed.
- Migration consistency: passed; `makemigrations --check` reports no model changes.
- PostgreSQL 18 migration state: all migrations applied through `communications.0003_whatsappconsent` and `phase3.0008_googlesigninstate`; `manage.py migrate` reports no pending migrations.
- Backend suite: 38 passed against the configured PostgreSQL 18 database, including tax arithmetic/month-end review, consent audit/opt-out enforcement, and mocked Gmail/sign-in OAuth flows with state replay and workspace checks.
- Frontend TypeScript check and Vitest suite: passed (`npm run typecheck`; 1 UI test).
- Gmail OAuth callback, account authorization configuration, read-only scope, encrypted token persistence, and state replay prevention are covered with provider responses mocked; live Google consent is not exercised in CI.
- Local development Fernet key format was validated. OpenAI/Meta credentials are not configured, so their live-provider flows remain disabled.
- Scheduled-worker behavior, SMTP delivery, and browser end-to-end flows remain deployment/integration checks.

## Unit tests

## Phase 2 coverage plan

Add focused tests for email message/attachment normalization and idempotency; unsupported-file quarantine; checksum and near-duplicate scoring/decisions; alias matching confidence and unapproved-vendor behavior; percentage/absolute matching tolerances; partial PO/GRN and service/freight evidence; approval rule priority, maker-checker, delegation windows, step history, and immutable evaluation snapshots; auto-approval eligible/ineligible controls; exception SLA countdown/escalation; follow-up draft/edit/no-send-by-default; full/partial/multiple payment allocations and overpayment constraints; pending versus approved note balances; custom-field validation; bulk preview token/expiry/per-record permission; notification preferences/read state; and date-filtered report/CSV tenant isolation.

Required invariants: no cross-tenant references; no auditor mutation; Purchase/Store cannot approve or record payments; no blocking exception/duplicate can reach payment-ready; no auto-approval when any required control fails; allocations cannot exceed net payable unless an explicitly audited policy is enabled; no outbound vendor message is sent without a user-confirmed send request; audit entries exist for every decision and financial action.

- Matching: vendor/item mapping, missing PO/GRN, quantity over receipt, rate tolerance boundaries, GST mismatch, duplicate checksum, and unapproved vendor.
- Invoice state transitions and version invalidation; manual creation with no extraction provider.
- Tally CSV headers, detail values, totals, rejection of open blocking exceptions, and balanced totals.
- Audit immutability and override reason requirements.

## Integration tests

- Registration, JWT login, membership roles, and tenant-scoped list/detail/update behavior.
- Upload validation, checksum persistence, duplicate detection, and document authorization.
- PO/GRN import validation, relationships, and unmatched records.
- Matching and exception persistence, assignment, resolution, and override audit.
- Approval/rejection with invoice version, actor, timestamp, comments, IP, and user agent.
- Export generation, CSV download, and invoice transition.
- Gmail OAuth read-only scope and encrypted refresh token; mocked mailbox sync imports an attachment once, repeat sync is idempotent, and non-finance roles cannot trigger sync. Never use live Google credentials in tests.
- Bank reconciliation suggestions enforce tenant scope and exact amount/date bounds, explain their reference/vendor evidence, and never change transaction state without an explicit match action.
- PO receipt tests cover multiple partial GRNs, default no-overage behavior, configured over-receipt tolerance, and rejection beyond the configured ceiling.
- Tally export tests verify tenant ledger mappings, category/rate/TDS/cost-center resolution, withheld-TDS gross balancing, and the payment-ready export gate.

## Frontend tests

Use Vitest and React Testing Library for dashboard rendering, status badges, form validation, loading/empty/error/permission states, upload, invoice review, and approval decision confirmation.

## End-to-end and acceptance

Use a synthetic tenant and deterministic fake extractor. Run 20 invoices with 5 vendors, 10 POs, 10 GRNs, 6+ exception cases, a duplicate, a missing GRN, and a rate variance. Confirm no blocking invoice reaches payment-ready/export before resolution and approval; reconcile export debit/credit and invoice count.

## CI gates

Run Django system checks, migration consistency, pytest, frontend lint/typecheck, Vitest, and production build. Use PostgreSQL/Redis for integration tests and do not depend on a live extraction provider.
