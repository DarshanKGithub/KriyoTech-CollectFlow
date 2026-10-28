# KriyoPay Product Plan

## Vision and positioning

**KriyoPay helps Indian SMEs stop paying incorrect supplier invoices by matching every invoice to its PO and GRN, flagging exceptions, and producing a Tally-ready payment record.** It is an invoice-to-payment control tower: a focused workflow around evidence, matching, approvals, and export rather than a replacement ERP.

## Target customer

Indian SME manufacturers, distributors, traders, and logistics businesses using Tally, Excel, email, and WhatsApp to manage accounts payable and purchasing. Initial pilots should have repeat suppliers, a usable PO/GRN process, and an owner or finance head willing to review payment controls.

## Buyer personas

- **Owner / Finance head:** wants control over cash outflow, clear exceptions, and approval evidence.
- **Accountant / AP executive:** captures invoices, reconciles records, fixes extraction errors, and prepares payment records.
- **Purchase manager:** investigates supplier, price, and PO discrepancies.
- **Store user:** confirms received quantities and corrects GRN links.
- **Approver:** makes deliberate approve/reject decisions with supporting evidence.
- **Auditor:** needs read-only access to source records, decisions, and immutable history.

## MVP scope

- Tenant signup, login, memberships, invitations, and role permissions.
- Vendor records; PO/PO-line and GRN/GRN-line entry and CSV imports.
- Invoice upload, checksum duplicate detection, pluggable extraction with manual fallback, and field correction.
- Deterministic three-way matching, exception queue, assignment, notes, reasoned overrides, and audit history.
- Approval and rejection workflow with comments and email notifications.
- Balanced Tally-ready purchase CSV export; no direct posting.
- Operations dashboard, audit log, settings for matching tolerances, sample imports, seed/demo data, host-based local setup, and deployment baseline.

## Explicit non-goals

Full procurement or inventory management; vendor portal; bank payments; GST filing; WhatsApp API; mobile apps; multi-currency; Kubernetes; microservices; direct Tally XML posting in MVP; autonomous AI approval or exception override; advanced BI.

## Adjacent module proposal

Transport customers may need truck, trip-cost, driver-pay, and follow-up controls. The proposed scope, workflows, data model, safeguards, and phased rollout are documented in [TRANSPORT_FLEET_MODULE.md](TRANSPORT_FLEET_MODULE.md). This is a separate, customer-validated module proposal; it is not part of the current AP MVP scope.

## Four-week roadmap

| Week | Focus | Exit outcome |
| --- | --- | --- |
| 1 | Foundation, tenant/auth/roles, vendor and procurement data, CSV templates | Tenant-isolated workspace; users can manage vendors, POs, GRNs |
| 2 | Invoice intake, storage, extraction adapter, review and duplicate detection | Invoice can be uploaded or manually entered, reviewed, and versioned |
| 3 | Matching, exceptions, audit, assignment and approvals | Blocking exceptions stop payment readiness; approval decisions are recorded |
| 4 | Tally CSV, dashboard, operational UI, seed data, deployment and pilot hardening | A finance team can process a realistic 20-invoice pilot and export balanced vouchers |

## Customer validation plan

1. Interview 5–8 target finance/accounting users and map the current invoice-to-payment process, exception types, and source systems.
2. Collect anonymized invoice, PO, and GRN examples (including problematic cases) with consent; define a representative pilot set of at least 20 invoices.
3. Test import templates and matching rules with finance and purchase users; record false matches and missing source data.
4. Observe a pilot user completing upload-to-review and exception resolution; measure time and correction frequency.
5. Review approval evidence and Tally CSV with the customer’s accountant before any live use; reconcile sample voucher totals.
6. Decide pilot continuation using acceptance criteria below and document unresolved workflow gaps.

## Pricing plan

| Plan | Price | Monthly invoice allowance |
| --- | ---: | ---: |
| Starter | ₹7,500/month | 100 |
| Growth | ₹15,000/month | 400 |
| Control | ₹30,000/month | 1,200 |
| Enterprise | Custom | Custom |

## Success metrics

- Invoice extraction review time under 3 minutes.
- At least 70% automatic line matching on clean pilot data.
- All blocking exceptions visible before payment-ready status.
- Audit trail for every state change.
- Tally-ready export with balanced debit and credit totals.

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Poorly structured or incomplete PO/GRN data | Provide templates, import feedback, manual edits, and unmatched-record queues |
| OCR/extraction errors | Field confidence, side-by-side source review, editable data, and manual entry fallback |
| False automatic matches | Deterministic rules, configurable tolerances, explainable variance details, and blocking ambiguity |
| Tenant data exposure | Tenant-scoped query services and permissions, isolation tests, and storage key scoping |
| Tally CSV incompatibility | Validate format with pilot accountants and provide reconciliation totals; describe it as CSV export, not direct integration |
| Approval bottlenecks | Aging dashboard, email notifications, clear assignments, and visible pending queues |
| Email/file processing failures | Retryable jobs, idempotency, failure states, and manual upload/entry fallback |

## Phase 2: Automation, flexibility, and control

### Delivery status

- **Implemented MVP:** tenant signup/auth and isolation, vendor/PO/GRN records and imports, invoice upload and manual review, deterministic matching, exceptions, single-step approval, immutable audit events, matching tolerances, and Tally CSV export.
- **Phase 2 implemented:** idempotent token-authenticated email attachment webhook, alias-assisted vendor matching, exact/near duplicate decisions, tenant matching settings, multi-step approval/delegation/history, strict guarded auto-approval, exception SLA/escalation, explicit-send vendor drafts, payment allocation/credit-debit notes, invoice custom fields, preview/commit exception bulk actions, in-app notifications/preferences, and operational reports/month-end readiness.
- **Phase 2 operational limits:** provider-specific polling/OCR and scheduled workers are not configured; SLA escalation is owner/finance-triggered; bulk operations currently cover exceptions.
- **Future/out of scope:** direct Tally XML posting, bank/UPI initiation, WhatsApp sending, unattended IMAP/Gmail/Graph polling, production OCR provider credentials, and AI approval. Email-provider integrations and AI extraction remain adapter-based and require explicit tenant configuration/consent.

### Phase 2 implementation sequence

1. Add tenant-owned schema, indexes, additive migrations, serializers, and permission checks; preserve all existing MVP endpoints.
2. Implement idempotent email ingestion, vendor aliases/suggestions, duplicate review, and configurable matching settings.
3. Add approval rules/history/delegation and auto-approval eligibility checks that cannot bypass blocking exceptions or human-control settings.
4. Add exception SLAs/escalations and editable follow-up drafts; sending always requires an explicit user action.
5. Add payment-ready, payment allocation, and credit/debit-note ledgers with transactional balance constraints and audit events.
6. Add custom fields, previewed bulk operations, notifications/preferences, reports, and month-end readiness.
7. Add tenant-isolation, financial-control, idempotency, workflow, and export tests; update onboarding and operational guidance.

### Phase 2 control invariants

- Every new business row is tenant-scoped and every reference is resolved inside the active tenant.
- Automation evaluates configured rules and records its inputs/results. It cannot override a blocking exception, duplicate decision, or tenant/user approval control.
- Payment records are append-only allocations; totals cannot exceed outstanding net payable without an explicit, audited overpayment policy.
- Outbound vendor contact is stored as a draft until a user reviews and sends it. Provider adapters do not send implicitly.
- Bulk actions preview affected records and use per-record authorization/audit events; long-running work is idempotent and observable.

## Phase 3: Supplier communication and operational controls

Phase 3 is sequenced in [PHASE3_PLAN.md](PHASE3_PLAN.md). Its first vertical slice implements tenant-mapped WhatsApp Business webhook intake, invoice attachment drafts, message history, and consent-gated, human-reviewed outbound message drafts. Meta credentials and an approved template are required for actual sending. Next come GST/TDS checks, bank statement reconciliation, PO/GRN creation and return handling. Native Tally posting follows customer validation of CSV. Company/branch scopes, workflow builder, vendor portal, public integrations, and advanced AI follow those foundations.

## Pilot acceptance criteria

- A tenant can invite users with role-limited access and cannot access another tenant’s records.
- Finance can upload or manually enter 20 invoices and edit extracted fields.
- Sample PO/GRN imports validate with row-level errors and retain source references.
- Demo cases include at least 6 exception scenarios, at least 1 duplicate, 1 missing GRN, and 1 rate variance.
- Any blocking exception prevents payment-ready or export; every override has a reason and audit entry.
- Approval/rejection records actor, timestamp, comments, and invoice version.
- Exported sample vouchers balance debit and credit and can be reconciled by a pilot accountant.
- Core matching, duplicate, permission, tenant-isolation, approval, and export behaviors are covered by tests before live pilot use.
