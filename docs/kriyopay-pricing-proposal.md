# KriyoPay Basic, Pro and Enterprise — pricing proposal

> Historical first proposal. The revised market-informed recommendation is in [KriyoPay market pricing review](kriyopay-market-pricing-review-2026-10-23.md). Neither proposal changes the live billing catalog.

Prepared 23 October 2026. Commercial design for review, not an activated billing catalog or a statement of production readiness. Prices and service targets below are proposed. Hosting, extraction and support costs have not been measured; validate margins and willingness to pay in paid pilots before publishing.

## Positioning

KriyoPay helps Indian businesses control supplier invoices from receipt through matching, approval, payment recording and accounting handoff. Sell fewer manual checks, clearer accountability and faster review. Savings require customer measurement; do not promise a percentage reduction in costs or errors.

Use company/workspace subscription + invoice volume + included staff seats. Avoid a percentage of supplier payment value: payment recording and accounting exports do not initiate bank transfers.

## Commercial structure

| Item | Basic | Pro | Enterprise |
|---|---|---|---|
| Monthly subscription | ₹7,500 | ₹15,000 | From ₹30,000 |
| Annual prepayment | ₹75,000 | ₹150,000 | From ₹300,000, negotiated |
| Effective monthly cost on annual billing | ₹6,250 | ₹12,500 | From ₹25,000 |
| Supplier invoices per subscription month | 100 | 400 | Starting allocation 1,200 |
| Named internal users | 3 | 10 | Starting allocation 25 |
| Company/workspace | 1 | 1 | 1 in starting package; additional entities quoted |
| Standard onboarding, one time | ₹5,000 | ₹15,000 | From ₹50,000 |
| Proposed support response target | 2 business days | 1 business day | 4 business hours for critical production incidents |

Annual pricing equals ten monthly payments for twelve months (16.7% saving). Subscription prices exclude applicable taxes. Enterprise starting prices apply to the baseline scope, not unlimited entities, transactions, custom engineering or infrastructure. Support operates Monday–Friday, 9:30am–6pm IST, excluding published holidays. Targets are first responses, not guaranteed resolutions. Contractual SLA and service credits require an operationally supported agreement.

## Basic — get invoices under control

Buyer: an owner, accountant and finance operator handling up to 100 supplier invoices monthly.

- Upload invoices and supporting files; enter or correct invoice fields manually.
- AI-assisted extraction within the document allowance; every extracted invoice remains subject to human review.
- Maintain supplier records and invoice status.
- Create purchase orders and goods receipts, including cumulative partial receipts; compare invoice, PO and received quantities/amounts and review exceptions.
- Flag potential duplicates for investigation. Do not describe duplicate screening as fraud prevention or a guarantee.
- Route invoices through a simple approval workflow; preserve review decisions and activity history.
- Record payment references, partial payments and balances; see paid, unpaid and overdue invoices.
- Export a reviewed Tally-ready CSV using configured ledger mappings.
- View standard invoice, outstanding-payable and exception summaries.
- Use core role permissions, workspace separation and record history as baseline controls across all tiers.
- Receive one remote onboarding session covering suppliers, document entry, matching and CSV export.

Basic boundaries: no automated email intake, vendor portal, multi-level routing, rule-based auto-approval, bulk processing, direct ERP connectivity or public API entitlement in the proposed package. Core review and approval must remain usable; avoid withholding basic financial safeguards to force upgrades.

Example: upload a supplier invoice, review the extracted fields, compare it with the PO and partial receipts, resolve a quantity discrepancy, obtain approval, export to Tally and record the eventual payment reference.

## Pro — automate the finance team's daily work

Buyer: a finance team processing up to 400 invoices monthly with several approvers. Includes Basic plus:

- Connected email/Gmail invoice intake, with provider configuration and permission requirements. Current Gmail sync is bounded and read-only; do not advertise unlimited real-time mailbox processing.
- Vendor portal submission, invoice-status visibility and questions/replies. Current portal links require controlled distribution; automatic invitation email is not included by default.
- Multi-level approval routing using supported workflow rules, with rejection and exception review.
- Eligible rule-based auto-approval after configuration and acceptance testing; never imply exceptions or required controls are bypassed.
- Credit/debit note handling, supported custom fields and bulk actions, subject to their normal permission and review checks.
- Bank statement import and reconciliation using supported CSV/XLSX mappings and exact amount matching. No live bank feed or arbitrary fuzzy matching promise.
- Operational tax arithmetic/format flags and a month-end review checklist. No government GST verification or statutory filing promise.
- Broader operational reports on invoice aging, approval backlogs and exceptions, limited to available reports. Custom BI is a separate scope.
- Two remote onboarding/training sessions, workflow setup and a review of the customer's Tally CSV mappings.
- Priority support under the business-hours target above.

Pro boundaries: direct ERP connections, API/webhook entitlement, multi-entity deployment, SSO and bespoke development require Enterprise or a separately scoped agreement. Advanced reports must be individually verified before listing them in sales materials.

Example: finance imports incoming invoices, suppliers answer questions in the portal, department and finance approvers review supported approval steps, and the accountant reconciles recorded payments against an uploaded bank statement.

## Enterprise — connect accounting systems and scale implementation

Buyer: a business with higher document volume, integration needs or a structured implementation project. Includes Pro plus:

- A starting allowance of 1,200 supplier invoices monthly and 25 internal users; negotiate larger allocations explicitly.
- One standard ERP connector configuration for one company in the baseline scope: TallyPrime, ERPNext or Zoho Books. Third-party licenses, local connectivity and provider accounts are supplied by the customer.
- Reviewed mapping, import staging, approved export snapshots, sync history and conflict/reconciliation review for supported resources.
- Customer sandbox acceptance before enabling financial writes. Tally inventory PO/receipt writes are not implemented. ERPNext exports are drafts; Zoho receipts require the separate Inventory companion connector. ERPNext/Zoho invoice export has withholding limitations. See the ERP document for exact resource support.
- Read-only API keys and signed outgoing webhooks within verified endpoint/event coverage. Do not advertise a general-purpose write API. Scheduled webhook delivery requires operated workers.
- An implementation lead, mapping workshop, documented acceptance checklist, training and a scheduled quarterly adoption review.
- A defined critical-incident escalation path. A dedicated support team or 24/7 coverage requires separate staffing and pricing.
- Dynamics 365 Finance, extra ERP companies, additional legal entities, historical migrations, custom mappings and custom reporting as individually priced implementation scopes.

Enterprise options requiring delivery validation: multi-company administration and consolidated reporting, enforced branch-level record isolation, SSO, dedicated hosting, contractual uptime commitments and custom retention/residency. These are not included promises merely because Enterprise has a feature flag.

Example: a finance team reviews matched invoices in KriyoPay and sends approved accounting records through a validated ERP mapping; uncertain remote writes go to reconciliation rather than being repeated blindly.

## Optional Fleet & Trips module

Keep fleet operations optional so non-transport customers do not fund an unrelated module. Offer it with Pro and Enterprise after module acceptance testing.

Suggested pilot price: ₹5,000/workspace/month for up to 25 active vehicles and 500 new trips monthly; expansion quoted until usage costs are understood.

Scope: vehicle/driver/customer records, transport orders, dispatch/trip milestones, delivery proof, reviewed trip costs, customer invoices and collections, supported per-trip/per-kilometre driver earnings, advances and recoveries, settlement review, receipts, follow-ups and operational margin reports. Customer receivables remain separate from supplier payables.

Exclusions: GPS hardware/live tracking, route optimization, FASTag or fuel-card integrations, statutory payroll, bank transfers and autonomous messaging. Price and vehicle/trip counters are proposals; their enforcement has not been established.

## Add-ons and upgrade boundaries

| Proposed add-on | Commercial rule |
|---|---|
| Basic invoice pack | 100 additional invoices for ₹2,500 in the current subscription month |
| Pro invoice pack | 200 additional invoices for ₹4,000 in the current subscription month |
| Additional internal seat | ₹500/month; max 2 extras on Basic and 10 extras on Pro |
| Enterprise volume/seats | Contracted allocation and unit rate |
| ERP implementation beyond baseline | Fixed scope and written quote |
| Historical migration | Quote after sample-data review |
| WhatsApp invoice intake | Quote only after provider, consent, configuration and production acceptance |
| Dedicated infrastructure or 24/7 support | Separate feasibility review and contract |

Basic at 400 invoices costs ₹15,000 with packs, making Pro the better upgrade because it includes more seats and automation. Pro at 1,200 invoices costs ₹31,000 with packs, making baseline Enterprise attractive. These boundaries avoid a permanently cheaper lower-tier substitute for the next plan.

Packs require explicit purchase; no surprise overage billing. Prorate recurring seat changes. Invoice packs expire at month end, with no rollover. Annual subscriptions still receive monthly document allowances.

## Metering definitions to implement

- One invoice unit means one distinct supplier invoice created by manual entry, import or intake. Failed uploads and rejected duplicates do not count. Deleting an accepted invoice does not reset the counter. Correcting fields or retrying a platform-failed extraction must not create another invoice charge.
- An AI allowance accompanies each included invoice: one extraction of up to five source pages. Larger documents or user-requested re-extractions need an explicitly priced additional allowance, to be set after cost measurement. Platform failures do not consume another customer allowance. Provider costs are included within this bounded allowance; customer-owned provider credentials require separate agreed terms.
- Count active internal members, including owners, finance users, approvers and auditors, against seats. Vendor portal identities do not consume internal seats. No shared staff logins.
- Supplier directory records and related PO/GRN records are included in ordinary use; publish concrete bulk/import/storage limits after load tests. Avoid describing storage as unlimited.
- Warn at 80% and 100% of the invoice allocation. At the limit, allow existing records to remain viewable, reviewable and exportable; stop new creation until capacity is added. This is proposed behavior, not confirmed current enforcement.
- Storage, retention, API throughput, webhook delivery limits and export-size limits must be quantified and disclosed before launch. Distinguish customer document retention from operational backup retention.

## Trial and commercial operations

Offer a staff-provisioned 14-day evaluation: 20 invoices, 2 staff users, core matching and a guided demonstration of selected Pro capabilities. Do not present it as an existing unrestricted self-service Pro trial. Use sample data or a limited customer pilot under agreed terms.

Upgrade when the customer buys capacity or needs higher-tier functionality. Downgrades take effect at renewal after limits and feature use are reviewed. Define cancellation, refund, export and post-cancellation retention terms in the customer agreement; avoid inventing an indefinite archive promise.

Separate subscription renewal payments via Razorpay from customers' supplier-payment records. Current renewal scheduling, grace operations and other billing lifecycle gaps need completion before promising autonomous subscription administration.

## Existing catalog migration

Current repository seed: Trial; Starter ₹7,500/100 invoices/3 users; Growth ₹15,000/400/10; Control ₹30,000/1,200 with an unlimited read-only-user description; Enterprise custom.

Proposed mapping: Starter → Basic, Growth → Pro, Control → baseline Enterprise, current Enterprise → negotiated Enterprise contracts. Preserve existing contracted allowances and grandfather terms rather than silently reducing access. The proposed 25-user Enterprise allocation differs from the existing Control definition.

Do not simply rename or rerun the seed command: it uses update_or_create and could overwrite configured terms. Version the catalog and migrate subscriptions deliberately. Keep stable entitlement identifiers independent of marketing plan names.

The revised split changes feature packaging. Existing Growth grants fleet; this proposal makes it an optional module for new contracts. Existing Control enables broad features; this proposal scopes ERP and API delivery explicitly. New portal/reconciliation/ERP/seat/storage limits may require additional entitlements and server enforcement. No live catalog or application behavior was changed to produce this proposal.

## Release and commercial validation

Repository documentation identifies unfinished production deployment/storage/backups, administrative MFA and consistent branch isolation. The ERP framework is not certified against a customer ERP. Feature flags do not establish production readiness. Close these gaps and validate tenant/permission checks before a general commercial launch; do not sell incomplete Enterprise options as available.

Measure cloud/database/storage cost, successful extraction cost per invoice/page, provider retries, email volume, onboarding labor and monthly support labor during pilots. Proposed recurring gross-margin target: at least 75%, excluding one-time implementation revenue and labor. This leaves monthly recurring direct-cost budgets of ₹1,875/₹3,750/₹7,500 at list prices, or ₹1,562.50/₹3,125/₹6,250 at annual effective prices. These are target ceilings, not measured costs. Reprice allowances if support or extraction costs exceed them.

Basic implies ₹75 per included invoice and Pro ₹37.50 at full monthly use; therefore demonstrate matching, approval and accounting-handoff value in pilots. The proposed price is anchored to the repository's current catalog, not validated market willingness to pay.

## Sources

- Repository: README.md, SUBSCRIPTION_PLAN.md, FEATURE_ENTITLEMENTS.md, backend/admin_console/management/commands/seed_admin_catalog.py, docs/erp-integrations.md, docs/critical-readiness.md.
- Public packaging reference checked 23 October 2026: https://www.zoho.com/in/books/pricing/ — bills per organization/month with monthly/annual options and separate user/document-scan add-ons. This supports the packaging pattern only; it does not validate KriyoPay's price points or imply feature parity.
