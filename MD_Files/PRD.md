# KriyoPay Product Requirements Document

## Product summary

KriyoPay is a multi-tenant accounts-payable control tower for Indian SMEs. It reconciles supplier invoices against purchase orders and goods-received notes, makes discrepancies visible before payment, records approvals, and creates a Tally-ready purchase CSV.

## Users and roles

Roles: `OWNER`, `FINANCE`, `PURCHASE`, `STORE`, `APPROVER`, `AUDITOR`. An owner administers tenant settings and membership. Finance manages invoices, matching, approvals where authorized, and exports. Purchase manages vendors/POs and supplier/price exceptions. Store manages GRNs and receipt exceptions. Approver decides on submitted invoice versions. Auditor has read-only access to permitted tenant records and audit evidence. A tenant may grant more than one role through explicit memberships; role checks are enforced server-side.

## User stories and acceptance criteria

## Phase 2 requirements

### Delivery status

- **Implemented MVP:** signup/login, tenant isolation, roles, vendors and procurement imports, invoice upload/manual review, deterministic matching, exceptions, one-level approval, audit, and Tally CSV.
- **Phase 2 implemented:** token-authenticated idempotent email attachment webhook; alias and confidence-aware matching; exact/near duplicate review; configurable rate/quantity/tax controls; multi-step approval rules, delegation/history, guarded opt-in auto-approval; manually triggered exception SLA escalation; draft-and-explicit-send vendor follow-ups; payment allocation and maker-checker credit/debit notes; invoice custom fields; preview/commit exception bulk actions; in-app notifications/preferences; operational reports and month-end readiness.
- **Phase 2 operational limits:** no provider-specific email polling/OCR credentials or background scheduler is configured. SLA escalation is user-triggered, and bulk actions currently cover exceptions.
- **Future/out of scope:** autonomous AI approval, automatic outbound WhatsApp/email without confirmation, direct bank payment initiation, direct Tally XML, and provider-specific polling integrations beyond the provider-neutral webhook/adapter boundary.

## Phase 3 requirements

- **First slice delivered:** Meta WhatsApp webhook signature verification; tenant phone-number mapping; idempotent inbound text and supported invoice attachments; invoice source channel; conversation history and delivery states; reviewed message drafts for approval requests, payment reminders, and vendor clarifications; recipient-consent confirmation and explicit finance-user send action.
- **Setup required for live use:** Meta Business account, system-user token, app secret, webhook verify token, Graph API version, approved utility template, HTTPS callback, and consented vendor phone numbers.
- **Planned next:** one-time approver links, scheduled reminders, GST/TDS controls, bank statement reconciliation, procure-to-pay additions, Tally voucher posting after CSV validation, multi-company and branch access, workflow builder, vendor portal, API/webhooks, and assistive AI.
- **Safety boundaries:** WhatsApp sends always require human action; AI cannot send or approve. Tally posting, bank transfers, and vendor bank-detail changes require explicit internal review and audited controls.

### Financial control acceptance criteria

- A duplicate candidate remains blocking until an authorized user records `CONFIRM_DUPLICATE` or `NOT_DUPLICATE`, with rationale and immutable audit history.
- Vendor suggestions include confidence/method and aliases; unknown vendors remain unapproved.
- Approval rules produce ordered steps and a stored evaluation snapshot. Maker-checker prevents the submitting user from approving their own invoice when enabled. Delegation is bounded by tenant, date range, and role.
- Auto-approval is disabled by default. When enabled, it requires approved vendor, clear duplicate state, full PO/GRN match, no blocking exception/high-risk flag, tax validation, amount within limit, and passing maker-checker policy. No AI output may satisfy an approval step.
- SLA clocks and escalation levels are visible and auditable. Notifications and follow-up messages do not themselves change invoice/payment state.
- Payment allocation is append-only, scoped to the active tenant, cannot exceed outstanding net payable unless an explicit audited policy allows it, and supports multiple partial payments.
- Credit/debit notes affect outstanding only after approval and retain links to the original invoice/GRN and reason.
- Bulk preview shows record counts and IDs before execution. Every mutation is revalidated per record and logged individually; any ineligible approval is skipped/rejected without partial unauthorized state changes.
- Reports are tenant-scoped, date/filter aware, downloadable as CSV, and do not claim bank reconciliation without imported bank evidence.

### Tenant access and setup

- As an owner, I can register a company and admin account with a unique workspace identifier. Registration creates a tenant and owner membership atomically.
- As an owner/admin, I can invite a user by email and assign a role. Invitation tokens expire, are single-use, and cannot grant access outside the tenant.
- As a user, I can log in, log out, and see my tenant and role. Every list and object endpoint scopes to that tenant.
- As an owner, I can set matching tolerances, duplicate rules, email intake address, and export ledgers.

### Vendor and procurement data

- As Finance/Purchase, I can create and edit vendors with GSTIN and approval status.
- As Purchase, I can import or manually create PO headers and lines. Import reports accepted/rejected rows and errors; repeated external PO identifiers are handled according to the documented tenant uniqueness rule.
- As Store, I can import or manually create GRNs and lines linked to PO lines. Unmatched PO and GRN records are visible.
- Users can download CSV templates with examples and required columns.

### Invoice intake and review

- As Finance, I can upload PDF, JPG, PNG, or HEIC invoices by drag-and-drop or file picker. Unsupported, oversized, or invalid files receive clear errors.
- The system stores the original, checksum, uploader/source, and timestamps. A repeated checksum is flagged as a duplicate candidate within the tenant.
- Extraction is asynchronous and provider-pluggable. The UI shows field-level confidence and source preview. Low confidence or failure permits manual entry.
- I can edit every invoice header and line field, then confirm a version. AI output cannot approve invoices.
- I can create an invoice manually without an uploaded document or extraction provider.

### Matching and exceptions

- On confirmation or explicit rerun, deterministic matching checks supplier, PO, item, received quantity, rate, tax, and TDS conditions.
- A `MATCHED` outcome is allowed only when all lines pass and no blocking exception remains.
- The exception queue supports status, vendor, code, severity, assignee, and date filters. It displays invoice preview, extracted fields, PO/GRN evidence, and comparison details.
- Finance can assign an exception to Finance, Purchase, or Store. Resolution requires a note. An override requires a reason and records actor/time in audit history.
- Any blocking exception prevents `PAYMENT_READY` and export.

### Approval and export

- Finance submits an eligible invoice for approval. The system records the submitted invoice version and notifies authorized approvers by email with a secure link.
- Approver can approve or reject with comments. The decision records approver, time, comments, version, and available IP/user-agent. Rejection returns the invoice to review/exception work.
- Only approved eligible invoices can be exported. Export validates debit equals credit, generates a Tally-ready CSV, marks the invoice exported, and records an audit event.

### Dashboard and audit

- Dashboard reports counts and values by status, exception types, vendor exception counts, duplicates, payment-ready invoices, approval aging, and monthly invoice volume.
- Audit log is tenant-filtered and read-only, with filters by action, user, object, and date. Important state changes and overrides are represented.

## Invoice statuses

`UPLOADED`, `EXTRACTING`, `EXTRACTION_FAILED`, `REVIEW_REQUIRED`, `MATCHED`, `EXCEPTION`, `APPROVAL_PENDING`, `APPROVED`, `REJECTED`, `PAYMENT_READY`, `EXPORTED`. Transitions must be explicit and validated. `PAYMENT_READY` requires approval, completed matching, and no blocking exceptions. `EXPORTED` requires a successful balanced export. `REJECTED` returns to review/exception state when corrected or resubmitted.

## Functional requirements

- Support tenant signup, login/logout/me, invitations, and role changes.
- Support vendors, PO/GRN import and manual CRUD, with template downloads and validation diagnostics.
- Support invoice upload/manual creation, extraction, correction/versioning, duplicate detection, matching, exceptions, approvals, email notification, exports, dashboard, and audit log.
- Provide a dedicated tenant inbound email address and adapter boundary; actual provider-specific webhook/IMAP configuration is deploy-time integration.
- Provide secure document preview/download after authorization.

## Non-functional requirements

- Strict tenant isolation for every business record and stored object.
- UUID primary keys, PostgreSQL constraints/indexes, transactional state changes, and append-only audit records.
- Responsive desktop-first finance UI; clear loading, empty, error, and permission-denied states.
- Idempotent background jobs, bounded retries, operator-visible failure details, and structured logs.
- Extraction provider credentials and other secrets are environment/secret-manager configured; no secrets committed.
- Manual invoice entry remains available when OCR/AI is unavailable.

## MVP exclusions

Full procurement, inventory, vendor portal, bank payments, GST filing, WhatsApp Business API, mobile apps, multi-currency, direct Tally XML posting, autonomous AI decisions, advanced analytics, and Kubernetes/microservices.

## Pilot measures and acceptance

Review time under 3 minutes; at least 70% automatic line matching on clean pilot data; all blocking exceptions visible before payment-ready; audit trail for every state change; balanced export. Pilot acceptance includes 20 realistic invoices, at least six exception cases, one duplicate, one missing GRN, one rate variance, verified tenant permissions, and accountant reconciliation of the CSV.
