# KriyoPay Transport Fleet and Driver Finance Module

## 1. Purpose

This document proposes an adjacent KriyoPay module for small and mid-sized transport companies that operate multiple trucks. It gives owners and finance teams a controlled view of trip income and cost, driver salary or trip pay, money advanced and paid, outstanding balances, and follow-up work.

The module extends KriyoPay's financial-control approach into fleet operations. It is not part of the current invoice-to-payment workflow and is not a full fleet-management or logistics platform.

## 2. Problem to solve

Transport operators commonly track trucks, trips, driver advances, fuel, tolls, repairs, and salary in separate spreadsheets, notebooks, messaging threads, and accounting records. This makes it difficult to answer:

- How much did a truck or trip earn and cost?
- What expenses were unsupported by receipts or exceeded an expected amount?
- How much driver pay has accrued, been advanced, and been paid?
- What balance remains payable or recoverable for each driver?
- Which driver owes trip details, receipts, or a cash/advance settlement?
- Where are margins being lost, and what evidence supports that conclusion?

“Money loss” should be made measurable through explicit exception categories, not treated as an unexplained calculated number. Examples include unreceipted spend, fuel spend or consumption variance, unapproved repairs, excess advances, revenue shortfall, and negative trip margin.

## 3. Product fit and boundary

### Reuse from KriyoPay

- Tenant and membership isolation, UUID identifiers, and workspace selection.
- Existing user roles, with server-side permission checks.
- Approval workflows, maker-checker policy, audit history, notifications, exception queues, and reports where they fit.
- Existing financial amount conventions (INR and fixed-precision decimal values).
- Existing payment concepts only where semantics match; do not overload vendor invoice allocations to represent driver payroll.

### New domain concepts

- Fleet vehicle (truck), driver, trip, trip revenue, trip expense, driver earning, advance, settlement, and driver follow-up.

### Out of scope for the first release

- GPS/telematics, route optimization, dispatch planning, live vehicle tracking, FASTag/fuel-card integrations, automated odometer feeds, statutory payroll or labor-law calculations, bank transfer initiation, and autonomous WhatsApp/SMS communication.
- Full general ledger or replacement for Tally/accounting software.

## 4. Users and permissions

Initially reuse existing memberships and add scoped capabilities rather than introducing a parallel identity system:

| Capability | Suggested roles |
| --- | --- |
| View fleet, trips, and financial summaries | OWNER, FINANCE, AUDITOR |
| Create and edit trucks, drivers, trip drafts, and expense drafts | OWNER, FINANCE; optional new FLEET role |
| Submit trip expenses, receipts, and driver updates | Optional future DRIVER portal/user role; first release may use staff entry |
| Approve trip settlements, expenses, and pay runs | OWNER or authorized APPROVER/FINANCE, subject to maker-checker |
| Export and reconcile records | OWNER, FINANCE; AUDITOR read-only |

All authorization is tenant-scoped and enforced by the API. A driver should only see their own records if a driver-facing experience is added. Do not grant driver access by making records public or exposing a shared workspace token.

## 5. Core workflow

1. Finance registers a truck and driver and records the driver's agreed pay basis (monthly salary, per-trip amount, per-kilometre rate, or another explicitly configured basis).
2. A dispatcher or finance user creates a trip, assigns one truck and one driver, and captures origin, destination, dates, customer/reference, and expected revenue or freight charge.
3. During or after the trip, staff records revenue evidence and itemized expenses such as fuel, tolls, loading/unloading, permits, repairs, and miscellaneous spend. Receipts can be attached.
4. KriyoPay calculates trip totals and configurable variance indicators. It flags missing evidence and policy exceptions but does not declare fraud or infer a cause.
5. Authorized users review and approve the trip financials. Corrections after approval require a reason and are audited; finalized financial rows are not silently overwritten.
6. Driver earnings accrue under the selected pay policy. Advances and approved payments are allocated to a driver and, where appropriate, a trip or pay period. The driver ledger shows accrued, paid/advanced, deductions, and remaining payable.
7. Follow-up items track missing documents, confirmations, or settlements with owner, due date, status, reminders, and resolution evidence.
8. Finance reviews per-trip and per-truck margins, expense variances, driver outstanding balances, and aging follow-ups; approved records can be exported for accounting reconciliation.

## 6. Functional requirements

### 6.1 Fleet directory

- Create, edit, deactivate, and view trucks with registration number, make/model (optional), capacity (optional), ownership/lease type, and notes.
- Registration number is unique within a tenant after normalization. Inactive trucks remain linked to historical trips.
- Create, edit, deactivate, and view drivers with name, contact details, employee/reference code, pay basis, effective dates, and active status. Store only information needed for the workflow.
- Support truck and driver assignment history; do not overwrite history when assignments change.

### 6.2 Trips

- Create trips with a unique tenant-scoped trip/reference number, truck, driver, customer (optional), route, start/end timestamps, odometer readings (optional), expected/actual revenue, and status.
- Validate that truck and driver belong to the same tenant and are active for the trip dates.
- Permit draft and in-progress editing; submitted trips enter review; approved trips are finalized; rejected trips return with reviewer notes.
- A truck or driver may not have overlapping active trips by default. If exceptions are allowed, require an explicit override reason.
- Track source and evidence for amounts (manual entry, import, or future integration).

### 6.3 Trip income and expenses

- Record line items with category, amount, transaction date, payee, payment method/reference, notes, evidence attachments, and whether the line is estimated or actual.
- Initial expense categories: fuel, toll/FASTag, loading/unloading, food/allowance, permit, repair/maintenance, parking, commission, and other. Tenant admins may configure additional categories.
- Record planned/budgeted amount where known and compute variance to actual using tenant-configured thresholds.
- Flag missing receipt based on policy and amount threshold; allow a reasoned exception for cases where a receipt is unavailable.
- Show gross trip margin as revenue minus approved trip expenses. Clearly label margin as incomplete while relevant trip values remain estimated or unreviewed.
- Preserve correction history and approval state. Attachments follow existing private document storage and authorization rules.

### 6.4 Driver pay, advances, and settlement

- Support a driver pay policy with an effective date range and explicit basis: fixed monthly salary, per-trip, per-kilometre, or manually agreed amount. Initial release may implement monthly and per-trip, with other bases kept configurable/planned until customer validation.
- Record earnings by pay period and/or completed trip. Store the calculation inputs and policy version used so a later policy change does not alter historical earnings.
- Record advances and payments as distinct immutable ledger transactions, with amount, date, method/reference, creator, approver, and optional trip/pay-period allocation.
- Show for each driver: opening balance, earnings, advances, approved deductions, payments, and closing payable/recoverable balance. Define sign conventions in UI and exports.
- Prevent payment/advance allocations from exceeding the eligible outstanding balance unless an authorized, reasoned override is recorded.
- Deductions require a category, supporting reason, approval, and audit history. Do not apply arbitrary or automatic deductions.
- A settlement/pay run has draft, submitted, approved, paid/part-paid, and cancelled/reversed states. Corrections use linked reversing entries rather than deleting paid transactions.
- The module is an operational driver ledger, not a statutory payroll engine. Tax, benefits, statutory deductions, and employment compliance are outside the initial scope.

### 6.5 Follow-ups and exception handling

- Create follow-ups from a trip, expense, driver balance, or truck with category, assignee, due date, priority, description, and evidence requested.
- Initial categories: missing receipt, missing trip details, fuel variance review, repair approval, advance settlement, driver confirmation, and other.
- Support open, in-progress, resolved, and waived states. Resolution or waiver records actor, time, and note/evidence; waiver requires a reason.
- Show overdue follow-ups and exception counts on the dashboard. Notifications remind an internal assignee; external driver messages require a reviewed draft and explicit send action, consent, and configured provider.
- Follow-up completion never automatically changes payment or approval state.

### 6.6 Reports and exports

- Fleet overview: active trucks, trips in progress, trips awaiting review, open follow-ups, and outstanding driver balances.
- Trip profitability: revenue, expense by category, gross margin, margin percentage where revenue is positive, and evidence/review status.
- Truck performance: trip count, revenue, expense, margin, distance when available, and fuel metrics only when reliable odometer/fuel quantities exist.
- Driver ledger: earnings, advances, deductions, payments, balance, and aging by pay period.
- Expense control: budget/actual variance, missing receipts, unapproved expenses, and unresolved exceptions.
- Reports are tenant-scoped, date/filter aware, exportable as CSV, and clearly distinguish estimated, submitted, approved, and paid amounts.
- Exports are data interchange for accounting review; do not describe them as direct Tally posting unless a separately validated integration is implemented.

## 7. Proposed data model

Follow KriyoPay conventions: UUID primary keys, tenant FK on every tenant-owned table, INR `NUMERIC(18,2)` amounts, UTC timestamps, service-layer same-tenant validation, indexes for common tenant/status/date queries, and append-only audit evidence for material actions.

| Entity | Main fields and constraints |
| --- | --- |
| `fleet_vehicles` | tenant, registration_number, make/model, capacity, ownership_type, status, notes; unique normalized registration per tenant |
| `fleet_drivers` | tenant, user link nullable, name, contact, reference_code, status; unique tenant/reference where present; restrict personal data |
| `driver_pay_policies` | tenant, driver, basis, rate/amount, currency, effective_from/to, active, approved_by; no overlapping active policy periods for same driver/basis |
| `fleet_trips` | tenant, trip_number, vehicle, driver, customer/reference, route, starts_at/ends_at, odometer_start/end, expected_revenue, actual_revenue, status, submitted/approved actors/times |
| `trip_revenue_lines` | tenant, trip, category/source, amount, transaction date, evidence/document, status; supports multiple revenue components |
| `trip_expense_lines` | tenant, trip, category, amount, transaction date, payee, payment method/reference, receipt/document, budgeted_amount, status, exception fields |
| `driver_ledger_entries` | tenant, driver, trip nullable, pay_period, entry_type (earning/advance/payment/deduction/reversal), amount, effective_at, reference, source_entry nullable, approval state, actor/approver; immutable after posting |
| `driver_settlements` | tenant, driver, period, gross earnings, adjustments, advances, paid amount, status, submitted/approved/paid metadata; totals reconcile to ledger entries |
| `fleet_follow_ups` | tenant, category, related object type/id, assignee, due_at, priority, status, description, resolution note/evidence, resolved_by/at; tenant-scoped relation validation |
| `fleet_assignment_history` | tenant, vehicle, driver, starts_at, ends_at, created_by; preserves assignment changes where dispatch assignment is distinct from a trip |
| `fleet_audit_events` or shared audit | Prefer existing append-only audit log with stable object types and before/after snapshots; avoid a second audit system unless storage policy requires it |

Use explicit decimal arithmetic and database checks for positive monetary amounts, nonnegative distance, and valid date ranges. Index `(tenant_id,status)`, `(tenant_id,driver_id,effective_at)`, `(tenant_id,vehicle_id,starts_at)`, `(tenant_id,due_at,status)`, and common trip/date reporting paths. Avoid a generic JSON-only ledger: typed transaction fields are needed for reconciliation and reporting.

## 8. Key calculations

All calculations must be explainable and derived from approved or clearly labeled provisional entries.

- **Trip gross margin** = approved actual revenue − approved actual trip expenses.
- **Driver balance payable** = opening payable + approved earnings − approved advances − approved deductions − approved payments. If the result is below zero, show a recoverable/advance balance distinctly rather than hiding the sign.
- **Expense variance** = actual amount − budgeted amount; thresholds are tenant-configurable, and a flagged variance requires review rather than being called a loss.
- **Fuel efficiency** is only calculated when both distance and fuel quantity are validated for the same trip or period. Fuel spend alone is not fuel efficiency.
- Never aggregate estimated or unapproved amounts into approved financial totals without a visible status distinction.

## 9. API and UI integration direction

Add a tenant-scoped `fleet` backend domain app (or a clearly bounded module if the current app structure calls for it), with serializers, permission policies, transactional services, routes under `/api/v1/fleet/`, and migrations. Suggested resource groups:

- `/vehicles`, `/drivers`, `/pay-policies`
- `/trips`, `/trips/{id}/submit`, `/trips/{id}/approve`, `/trips/{id}/reject`
- `/trips/{id}/revenue`, `/trips/{id}/expenses`
- `/drivers/{id}/ledger`, `/settlements`, `/settlements/{id}/approve`, `/settlements/{id}/mark-paid`
- `/follow-ups`, `/reports/trip-profitability`, `/reports/driver-balances`

Names are illustrative and should be aligned with existing router conventions before implementation. Add a `/fleet` UI area with overview, trucks, drivers, trips, driver settlements, follow-ups, and reports. Keep the existing invoice AP navigation and behavior intact; cross-link shared payment/export concepts only where the underlying records and accounting treatment are clear.

## 10. Security, audit, and financial controls

- Every API query and mutation is scoped to the active tenant and membership. Never trust tenant IDs supplied by the client without validating membership.
- Validate same-tenant ownership for vehicle, driver, trip, expense, settlement, follow-up, and document links.
- Use role/capability checks on the server; hide UI actions only as a usability aid.
- Apply maker-checker to settlement and configured high-value expense approvals. Record the policy evaluation and approver identity.
- Audit create, edit, submit, approve, reject, waive, pay, reverse, and export actions with actor, timestamp, reason, and relevant before/after values.
- Do not hard-delete trips or posted financial entries. Deactivate directory records and use reversal/void workflows.
- Store receipts in private tenant-scoped storage; use the existing authorization gate for preview/download.
- Use idempotency for payment/settlement endpoints and imports to avoid duplicate ledger entries.
- Driver messaging, payment initiation, and accounting posting remain human-confirmed actions.

## 11. Phased delivery plan

### Phase 0: customer discovery and policy decisions

Validate one transport customer's actual records and terminology. Decide salary basis, trip lifecycle, expense categories, receipt policy, advances/deductions, settlement period, approval thresholds, and what data is available for fuel analysis. Define baseline KPIs and sample reports before coding.

### Phase 1: fleet and trip cost visibility

Deliver truck/driver directory, trip entry, revenue and expense lines with private receipt upload, trip review, basic exceptions/follow-ups, and trip profitability report. Use staff-entered records. No payroll complexity, telematics, or automated outbound messaging.

### Phase 2: driver ledger and settlement

Add effective-dated pay policies, earnings accrual, advances, payments, maker-checker settlement approval, driver balances, and CSV export. Reconcile sample outputs with the customer's accountant before live financial use.

### Phase 3: reminders and integrations

Add scheduled internal reminders, then reviewed/consent-based driver messaging if the customer needs it. Evaluate fuel-card, FASTag, GPS, or Tally integrations only from validated customer demand and documented APIs/data agreements.

## 12. Acceptance criteria for a pilot

- A tenant can create trucks and drivers, and every record remains isolated from other tenants.
- A trip can be assigned, submitted, reviewed, and approved with an auditable history.
- Revenue and expense totals reconcile to line items; trip margin is clearly labeled by review status.
- Missing receipts and threshold variances appear as actionable exceptions with assignee and due date.
- A driver ledger reconciles earnings, advances, deductions, payments, reversals, and closing balance for a sample period.
- A settlement cannot be approved by its maker when maker-checker is enabled; paid entries cannot be edited or deleted.
- Follow-up resolution does not silently approve trips or change balances.
- CSV reports reconcile to the UI and show status, date range, and totals.
- Customer finance/accounting owner validates the policy and output on representative historical trips before production rollout.

## 13. Open product decisions

Resolve these with the pilot customer before finalizing implementation:

1. Are drivers employees, contractors, or both, and which pay arrangements apply?
2. Is “salary” fixed monthly, trip-based, distance-based, or a mix? What pay period and approval cycle are used?
3. Are advances and trip cash tracked separately today? How are recoveries/deductions approved?
4. What counts as trip income, and can a trip have multiple customer charges or partial collections?
5. Which expense types need budget/actual controls, and what receipt thresholds apply?
6. What does “money lost” mean to the owner? Which measurable cases should create alerts?
7. Is truck maintenance tied to trips, or does the customer also need a vehicle service schedule in a later phase?
8. Who enters trip data and receipts: finance staff, dispatchers, or drivers? Is a driver portal or mobile-first flow required?
9. Which existing accounting system receives the final data, and what import format has the accountant approved?
10. Are integrations such as FASTag, fuel cards, GPS, WhatsApp, or Tally required for the pilot, or can staff entry validate the workflow first?

## 14. Recommendation

Treat this as a validated adjacent vertical module for transport customers, not as a change to KriyoPay's core AP workflow. Start with trip income/expense visibility and evidence-backed exception handling, then add the driver ledger and settlement workflow after the customer confirms its pay rules. This keeps the first release useful while avoiding a premature payroll or fleet-management system.
