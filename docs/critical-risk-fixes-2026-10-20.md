# Critical risk fixes — 20 October 2026

## Scope and changes

This release addresses the six issues selected from the product risk review.

| Issue | Fix |
| --- | --- |
| Cross-company invoice document access | Invoice input restricts supplier and document references to the current workspace. Source downloads verify document ownership. Legacy foreign references are masked in responses, and extraction rejects foreign documents. |
| PostgreSQL fleet action and billing crashes | Fleet trip queries lock only the trip table with `select_for_update(of=("self",))`. Linked transport orders are locked separately, avoiding PostgreSQL's nullable outer join restriction. |
| Fleet alerts HTTP 500 | Prefetched alert query iteration uses an explicit chunk size. The fleet UI displays an error and retry action when alerts cannot load. |
| Payments before approval | A shared manual/ERP payment service requires PAYMENT_READY or EXPORTED invoices, an approved supplier, and no unresolved blocking exceptions. |
| Editing posted invoices | Approved, exported, payment-linked and approval-pending invoices reject field edits, deletion, rematching and re-extraction. A persistent financial lock protects posted records even if their workflow status is reset. Payment status is read-only in invoice input. |
| Concurrent overpayment | Manual and ERP payment writes lock invoices in deterministic order, recalculate active allocations, combine repeated invoice allocations, and reject amounts above the remaining balance. Identical idempotency requests replay; conflicting reuse returns HTTP 409. Credit/debit decisions also lock the invoice. |

The payment page now selects eligible unpaid/partially paid invoices and sends the correct supplier field. A partial payment requires the operator to enter the amount instead of defaulting to the original invoice total.

## Migration and local activation

`invoices.0007_invoice_financial_locked_at` adds the persistent lock and backfills approved, exported and payment-linked invoices. Applied to the local PostgreSQL database. Apply migrations before running this version in another environment.

The local Celery worker was restarted after confirming no active tasks. Django and the frontend use their existing development reloaders.

## Verification

- Full backend suite on SQLite: **160 passed, 5 skipped**. The skipped cases require PostgreSQL.
- Targeted financial controls and fleet regression suite on an isolated PostgreSQL database: **32 passed**, clean teardown.
- PostgreSQL cases include simultaneous different payment keys, exact concurrent replays, conflicting reuse across invoices, reversed allocation ordering, and fleet actions/billing with and without a transport order.
- Frontend tests: **10 passed**.
- TypeScript `tsc --noEmit`: passed.
- Django migration consistency check: no changes detected.

Regression coverage lives in `backend/invoices/test_financial_controls.py`. The earlier `.dev-runtime/audit_risk_repros.py` and `audit_pg_probe.py` are historical diagnostics that assert or demonstrate the original defects; use the regression suite above to assess the fixed behavior.

## Limits

This patch prevents the demonstrated access and payment defects. It does not repair historical accounting discrepancies or remove previously copied foreign document contents. Review existing records separately before client onboarding.

Branch isolation, administrator authentication hardening and production deployment configuration from the wider audit remain separate work. Real ERP account certification and production load testing are also outside these regression results.
