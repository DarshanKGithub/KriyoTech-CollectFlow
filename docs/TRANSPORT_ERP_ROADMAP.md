# KriyoPay Transport ERP: implementation roadmap

## Scope and guardrails

Extend the current KriyoPay web product in place. Keep Next.js, TypeScript, Tailwind, MUI, Django REST Framework, PostgreSQL, the existing authentication model, and Razorpay. Do not seed demo values into production workflows. Use migrations for schema changes and retain tenant scoping on every API.

This is an implementation plan, not a claim that the product already meets every listed ERP requirement. The repository has existing user changes; implementation should stay limited to the files needed for each phase.

## Architecture found in the repository

```text
Next.js App Router + TypeScript + Tailwind + MUI
  ├─ WorkspaceShell: tenant-aware navigation, JWT session, entitlements
  ├─ Screens call Django through the shared apiFetch client
  └─ Responsive web experience
       │ Bearer JWT + X-Workspace (+ X-Branch header support in CORS)
       ▼
Django 5 + Django REST Framework
  ├─ tenants / accounts: Tenant, Branch, Membership, BranchMembership
  ├─ fleet: orders, trips, vehicles, drivers, GPS history, maintenance, costs
  ├─ invoices / procurement / payments / settlements / ERP integrations
  └─ Redis + Celery for scheduled and background work
       ▼
PostgreSQL
```

## Phase zero audit

### In place and reusable

- Tenant records, workspace keys, JWT membership selection, invitation flow, and tenant-scoped APIs.
- Membership roles, feature entitlements, backend role checks, and frontend permission-filtered navigation.
- Branch directory and branch-to-member assignments.
- Existing Next.js application shell, responsive navigation, theme support, MUI/shadcn-style primitives, API client, and form components.
- Fleet operations include transport orders, dispatch planning, trips/stops, location history, geofences, fuel/cost records, maintenance, driver settlements, shipment links, and operational reports.
- Procurement, invoice review, approvals, payments, Razorpay platform billing, customer transport invoicing/collections, notifications, and audit records already have implementations.

### Material gaps and dependencies

- **Branch data isolation is incomplete.** Branch and membership-assignment tables exist, but core operational records are not consistently branch-bound. Branch-scoped memberships are denied access to APIs that are not marked branch-aware. Do not add a branch picker that implies business records are filtered until the API/queryset work is complete.
- **Roles are coarser than the target.** Existing roles include Owner, Finance, Purchase, Store, Approver, Auditor, Driver, and Fleet. Fine-grained resource/action permissions and HR/Inventory/Operations roles remain to be designed and enforced server-side.
- **LR/consignment notes:** logistics document upload/review existed; a structured LR issue/list/cancel/print first slice is now in progress. Configurable numbering, edits/reissue history and PDF service remain.
- **Accounting:** Tally exports and ERP adapters exist, but they are not a full general ledger, journal, trial balance, or financial statement system.
- **Inventory:** procurement/GRNs exist; stock ledger, warehouses, parts, and tyre movements were not found as a complete stock system.
- **Transport payment gateway:** preserve existing Razorpay subscription billing. Customer transport collection payment flows require separate verification before claiming gateway coverage.
- **Live updates:** GPS ingestion and history exist. A tenant-authorized Channels/WebSocket delivery path was not found in the reviewed architecture; verify polling/provider behavior before expanding real-time claims.
- **External government, vehicle, toll, fuel-card, and GPS providers** require official access, licensing, credentials, and cost review before integration.

### Branch-ready data relationship target

```text
Tenant ──< Branch
Tenant ──< Membership >── User
Membership ──< BranchMembership >── Branch

Tenant ──< Customer / Supplier / Vehicle / Driver / Booking / Trip / Invoice / StockItem
Branch ──< each branch-owned operational record (nullable during migration)
```

Every branch-aware request must validate that the selected branch belongs to the active tenant and is assigned to the member when branch scope is enabled. Querysets, creates, exports, reports, background jobs, and related-object lookups must apply the same scope. Add branch foreign keys with backward-compatible defaults/backfill; do not infer a branch from client input without validation.

## Phased delivery

| Phase | Focus | Exit condition |
|---|---|---|
| 1. Foundation | Tenant/branch data boundaries, RBAC model, shared shell, simple data-backed dashboard | Branch scope is enforced in API querysets and writes; permission matrix is documented; shell and dashboard show only authorized workflows; tenant-isolation tests pass. |
| 2. Transport operations | Customer/supplier CRM, bookings/orders, trip lifecycle, LR, dispatch, delivery/POD | End-to-end booking-to-POD workflow persists and audits all transitions. |
| 3. Fleet | Vehicle/driver completeness, tracking, routes, fuel, maintenance, documents | Asset histories and GPS state use real provider/device data and tenant-scoped access. |
| 4. Finance | Transport invoices, collections, Razorpay preservation, expenses, ledgers/accounting | Reconciled financial records and audited statements; no subscription billing regression. |
| 5. Inventory | Warehouses, items, stock ledger, parts, tyres, procurement integration | Stock movements are immutable/reconciled and support reorder reporting. |
| 6. Business management | HR/payroll, notifications, customer portal, workflow configuration | Roles, approvals, and external-facing portal access are tested end to end. |
| 7. Intelligence | AI assistant, OCR, automation, predictive reporting | AI output is labeled as suggestions and grounded in authorized records. |
| 8. Enterprise readiness | Security, performance, exports, backup/recovery, deployment | Operational runbooks, observability, recovery checks, and release verification are complete. |

## Phase 1 execution order

1. Specify the resource/action/role matrix and branch rules before adding new roles or UI controls.
2. Inventory models and API querysets that need a `Branch` relationship; identify default-branch backfill and cross-tenant protection.
3. Add branch-aware API context and queryset helpers, then migrate core transport records incrementally (orders, trips, vehicles, drivers, customers) with tests for tenant and branch isolation.
4. Add branch selection to the workspace shell only after the selected branch is validated and applied server-side to all relevant reads and writes.
5. Extend branch scope to finance and reports in separate migrations/API increments.
6. Keep the dashboard composed only from available API metrics; show an unavailable state when a metric is not supplied, never a fabricated zero.

## Work already started in this workspace

- The shared shell and design tokens were already present and have been extended in earlier work.
- The workspace dashboard was simplified to role-aware, API-backed fleet, attention, invoice, and finance sections.
- The audit log was changed from a generic raw grid to a searchable event list with a detail drawer and full available-width layout.
- The fleet primary action was restyled to use the KriyoPay green brand color.
- LR management is now the first new transport module slice: tenant/year sequence, immutable party/route/assignment snapshots, order/trip links, issue/cancel audit events, receipt register, preview and browser print.

These changes do not close the backend branch-isolation, configurable LR numbering/PDF and edit-history, accounting, or inventory gaps above. Phase 1's next backend milestone is the branch-aware resource/API inventory and permission matrix, followed by a narrow, tested migration slice. See [the feature comparison matrix](TRANSPORT_ERP_FEATURE_MATRIX.md) for the module-by-module gap review.

## Verification policy

For each code increment, run the relevant frontend typecheck/lint or Django model/API/permission tests. Run focused tests first, then broader suites when the dependency is stable. Keep production database contents untouched; use migrations and disposable test databases.
