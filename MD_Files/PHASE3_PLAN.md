# KriyoPay Phase 3 plan

Phase 3 extends the invoice control tower through supplier communication, compliance, payment reconciliation, and broader procure-to-pay workflows. The attached feature brief explicitly advises sequencing the work instead of building every epic at once.

## Delivery sequence

### 3.1 WhatsApp Business communication — first vertical slice

**Delivered in this increment:**

- Tenant-scoped Meta phone-number registration; access token, app secret, verification token, API version, and approved template remain backend environment configuration.
- Meta webhook verification and HMAC signature checks; inbound message IDs are idempotent.
- Supported invoice attachments are stored as workspace documents and create an `UPLOADED` invoice draft. A vendor is matched by its normalized contact phone when present; uncertain text is not linked to an invoice.
- Tenant-scoped message and delivery-status history linked to invoices where evidence permits.
- Approval-request, due-date reminder, and clarification drafts; explicit send requires vendor consent, a finance user action, Meta credentials, and a configured approved utility template. Draft/send actions are audited.
- Tenant-scoped consent register with finance-recorded evidence, actor/audit history, automated opt-out for inbound STOP/UNSUBSCRIBE/CANCEL/END/QUIT messages, and enforcement both when creating drafts and immediately before sending.
- Uncertain sends remain visibly unresolved after network timeouts; after five minutes, finance users can reconcile against Meta records with evidence and (for confirmed sends) the provider message ID. This never retries automatically.
- Delivery callbacks are monotonic: delayed `sent` or `delivered` events do not downgrade `READ` or `FAILED` states.

**Still needed for a customer-ready WhatsApp rollout:** secure one-time approver links, a two-step review/send experience for approval requests, template-specific parameter mappings, media-caption and multi-attachment handling, provider setup validation, verified opt-in evidence capture from a consent source, and automated reminder scheduling. This slice deliberately does not claim to be connected until credentials and a Meta Business number are configured.

### 3.2 GST and TDS controls

**Delivered in this increment:** tenant-scoped invoice tax review, GSTIN format flagging, missing HSN/SAC and invoice arithmetic flags, human-entered registration status, ITC decision/reason, e-invoice IRN reference, TDS section/rate and certificate reference, reviewer attribution, and audit log. UI is at `/compliance` and API is `GET/PATCH /api/v1/compliance/tax-reviews`.

**Delivered in this increment:** line-level GST arithmetic and invoice-total consistency flags, plus a tenant-scoped month-end operational checklist with finance review notes and audit attribution.

**Still needed:** live registration validation through an authorized provider, tax-rule effective dates and thresholds, and certificate lifecycle/attachments. The current checks are screening aids only and make no statutory determination; the checklist is not a statutory filing or tax-compliance certificate.

### 3.3 Bank reconciliation

**Delivered in this increment:** tenant-scoped UTF-8 CSV and XLSX statement import up to 10 MB with user-selected column headers, workbook expansion and row limits, file idempotency, duplicate-row flags, exact-amount payment matching, explicit reconciliation confirmation, undo, and audit events. UI is at `/bank-reconciliation` and API is `GET/POST/PATCH /api/v1/bank-reconciliation`.

**Delivered in this increment:** on-demand, tenant-scoped payment suggestions for unmatched transactions. Candidates require exact amount and a paid date within seven days; normalized bank/payment reference and vendor name evidence contribute to an explainable confidence score. A finance user still chooses the match, then separately confirms reconciliation.

**Still needed:** MT940/CAMT parsers, statement summaries/forecasting, partial matching, and exception resolution. No bank transfers are initiated.

### 3.4 Procurement completion

**Delivered in this increment:** PO draft creation with multi-line data, editable draft revisions with immutable snapshots and mandatory change reasons, submit/approve/reject state transitions, separate finance approval, GRNs created only from approved tenant POs, per-line receipt quantities, quality status/notes, and audit events. The `/purchase-orders` and `/grns` screens support these actions. Existing credit/debit notes cover approved return/adjustment requests.

**Delivered in this increment:** cumulative GRN receipt balances are enforced across multiple partial receipts and CSV import. Owner/finance users can set an audited 0–100% over-receipt tolerance (default 0%); received, remaining, and maximum receivable quantities appear on each PO line. Receipt operations lock the PO row to prevent concurrent over-receipt.

**Still needed:** quote revisions, inspection attachments, and richer return-to-vendor/replacement workflows.

### 3.5 Vendor portal — first vertical slice

**Delivered in this increment:** tenant/vendor-scoped links with random high-entropy tokens stored as hashes, 30-day default expiry (up to 90 days), manual revocation, request throttling, invoice upload with checksum deduplication, vendor-only invoice status, and invoice-specific portal questions. Workspace replies are visible in that invoice's portal conversation. Bank-detail changes are not collected or applied.

**Delivered follow-up:** workspace message inbox and invoice-specific portal replies are implemented at `/vendor-portal`; operators can reply in the supplier's portal conversation. The portal does not send email notifications.

**Still needed:** email delivery/invitation dispatch, vendor document management, bank-detail change requests with secure review, stronger file-content validation/virus scanning, and customer-specific link retention controls.

### 3.6 AI-assisted invoice review — first opt-in slice

**Delivered in this increment:** optional OpenAI Responses API and Google Gemini `generateContent` adapters using structured JSON output, owner-only provider selection and workspace enablement, finance user per-request confirmation, metadata-only sharing (no uploaded file), bounded request/output sizes, persisted evidence-labeled suggestions, and explicit keep/dismiss decisions. Suggestions never mutate invoice state or trigger another action. Keys stay backend-only in `OPENAI_API_KEY` or `GEMINI_API_KEY`; models can be set using `OPENAI_MODEL` or `GEMINI_MODEL`.

The response schema follows OpenAI's [Structured Outputs guidance](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses); model and account availability still depend on the user's OpenAI API account.

**Still needed:** duplicate-payment and delay prediction, cash forecast, natural-language search, month-end assistant and reviewable matching recommendations, eval sets/accuracy monitoring, provider retention/legal review, and other provider adapters. The model-reported confidence is uncalibrated.

### 3.7 Multi-company and workflow foundations

**Delivered foundation:** company workspaces are represented as tenant records; users with multiple active tenant memberships can switch workspaces after email/password sign-in. Owners can manage tenant-scoped branch records and assign active members to branches with audit events. The existing approval-rule builder supports priority, amount/category/vendor conditions, ordered approver roles/users, and due hours.

**Still needed:** branch-level filters and branch foreign keys across business records, branch-aware reporting, consolidated cross-company dashboards, intercompany handling, broader workflow conditions/statuses, configurable exception and Tally mappings, and workflow versioning. Branch assignment metadata is not yet an access boundary; do not treat it as one.

### 3.8 Accounting integration

**Delivered foundation:** balanced Tally CSV export now applies workspace-owned, audited mappings for voucher type, vendor, purchase category, GST rate, TDS section, and cost center. It balances gross purchase debit against net payable plus TDS withheld. Mappings affect future exports only; payment-ready and open-exception eligibility checks remain enforced.

First validate the CSV with pilot accountants and customer Tally versions; then design company selection, sandbox voucher posting, import failure handling, and reconciliation. Use TallyPrime's supported import protocol and a local connector/agent where required; do not expose a customer's local Tally HTTP listener to the public internet. Add masters incrementally, and never auto-post production accounting entries without a user-reviewed mapping and explicit action.

### 3.9 Expansion and platform capabilities

**Delivered foundation:** owner-managed API keys are hashed and currently grant read-only invoice access at `/api/v1/external/invoices`; webhook endpoints use encrypted signing secrets, public HTTPS validation, signed event payloads, a persistent outbox, bounded automatic retries, per-endpoint delivery history, and audited owner/finance manual retries capped at three retry cycles while preserving event IDs. A `deliver_webhooks` worker command performs delivery. Workspace switching uses active memberships and keeps tenant isolation. Conditional approval rules and ordered steps already exist, and AI review is opt-in and reviewable. Gmail requests read-only access, verifies account identity, stores the refresh token encrypted, and manually syncs up to 25 messages from the last 30 days through idempotent invoice attachment intake.

**Still needed:** branch-level access filters, company consolidation/intercompany data, a general workflow designer with custom states/escalation/mapping, writable scoped API access, webhook scheduler deployment, a wider connector catalog, bank-detail change workflow, and the remaining AI assistants. Worker delivery still runs only when `python manage.py deliver_webhooks` is scheduled or run by an operator; no Windows service or scheduler was provisioned.

## Acceptance gates

- Every Phase 3 business object is tenant scoped and audited; cross-tenant references fail closed.
- External communication requires recorded consent and a deliberate human send action.
- Imported financial lines are idempotent, traceable to source files, and never silently marked reconciled.
- Tally posts, when added, are idempotent and reconcile the exact voucher response to the source invoice.
- Compliance checks describe their evidence and confidence; no result implies legal/tax advice or live government validation without an authorized source.
- New capabilities pass backend permission/tenant/invariant tests, frontend type checks, and representative customer workflow review.

## WhatsApp integration setup

Set these variables in the backend environment, never in browser JavaScript:

- `WHATSAPP_ACCESS_TOKEN`: Meta system-user access token with WhatsApp messaging permissions.
- `WHATSAPP_APP_SECRET`: Meta app secret used to validate webhook signatures.
- `WHATSAPP_VERIFY_TOKEN`: random value configured in the Meta webhook registration.
- `WHATSAPP_GRAPH_API_VERSION`: Graph API version enabled for the Meta app (for example, the version shown in its dashboard).
- `WHATSAPP_APPROVED_TEMPLATE`: approved utility template with one body placeholder for the reviewed message text.
- `WHATSAPP_TEMPLATE_LANGUAGE`: approved template language code.

Register `/api/v1/whatsapp/webhook` as the HTTPS webhook callback and subscribe to the WhatsApp `messages` field. Connect each workspace's Meta phone-number ID in the WhatsApp page. Vendor phone numbers should include country code and be recorded in vendor details. Store and retain only the minimum conversation data needed for invoice operations and customer retention policy.
