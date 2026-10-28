# KriyoPay REST API Specification

Base path: `/api/v1/`. JSON requests/responses except multipart uploads and CSV downloads. Authentication uses secure session cookies or JWT configured for the deployment. The server derives tenant scope from authenticated membership; clients do not choose arbitrary tenant IDs. UUIDs identify resources but every lookup is tenant-scoped.

## Common behavior

- List responses: `{ "count": 0, "next": null, "previous": null, "results": [] }` with `page`/`page_size` pagination.
- Structured error: `{ "error": { "code": "VALIDATION_ERROR", "message": "...", "details": {}, "request_id": "..." } }`.
- Codes: `AUTHENTICATION_REQUIRED` (401), `PERMISSION_DENIED` (403), `NOT_FOUND` (404, including cross-tenant object), `VALIDATION_ERROR` (400), `STATE_CONFLICT` (409), `RATE_LIMITED` (429), `INTERNAL_ERROR` (500).
- List endpoints accept documented filters and safe ordering; serializers validate all writes. Mutations use idempotency keys where a retry could duplicate an operation.

## Endpoints

## Phase 2 API additions

All routes below are under `/api/v1/`, require JWT and an active tenant membership unless explicitly marked as a signed/provider-authenticated webhook. Every write validates object tenant scope, role, current state, and idempotency where applicable. Exact response schemas are added alongside each endpoint implementation.

| Method and path | Purpose / access |
| --- | --- |
| `POST /email-ingestion/webhook` | Provider-authenticated normalized email payload; idempotent by tenant/provider/message ID; accepts multiple attachments |
| `GET /email-ingestion/logs` | Tenant-scoped ingestion status/failure list; owner/finance |
| `POST,GET /vendors/{id}/aliases` | Manage vendor aliases; owner/finance/purchase |
| `GET /duplicate-checks` | Tenant duplicate candidates, similarity reasons, and decisions |
| `POST /duplicate-checks/{id}/resolve` | `CONFIRM_DUPLICATE` or `NOT_DUPLICATE` with mandatory rationale |
| `GET,POST /approval-rules`; `PATCH,DELETE /approval-rules/{id}` | Manage validated tenant approval rules; owner/finance; delete is soft deactivate and audited |
| `GET /approvals/pending`; `POST /approvals/{id}/delegate`; `GET /approvals/{id}/history` | Approval queue, bounded delegation, immutable approval-step history |
| `GET,POST,PATCH /auto-approval-rules` | Owner-controlled rules, disabled by default; every evaluation persisted |
| `GET /exceptions/overdue`; `POST /exceptions/bulk-assign`; `POST /exceptions/bulk-resolve` | SLA queue and preview-token protected bulk actions |
| `GET,POST /invoices/{id}/follow-ups`; `PATCH /follow-ups/{id}` | Create/edit message drafts, then explicitly send; history is retained |
| `GET /payment-ready`; `GET,POST /payments`; `GET /payments`; `GET /invoices/{id}/payments` | Register, payment entry/allocation and invoice history; finance/owner writes |
| `GET,POST /credit-notes`; `GET,POST /debit-notes` | Create pending notes and approve via explicit workflow before balance effect |
| `GET,PATCH /matching-settings` | Tenant-specific matching priorities and rate/quantity/tax tolerance |
| `GET,POST /custom-fields`; `PATCH /custom-fields/{id}` | Manage typed tenant custom-field definitions and values |
| `POST /bulk-jobs`; `GET /bulk-jobs/{id}` | Preview then enqueue authorized bulk operation; status/progress/result |
| `GET /notifications`; `PATCH /notifications/{id}/read`; `GET,PATCH /notification-preferences` | Tenant/user notification center and preferences |
| `GET /reports/{invoice-aging,vendor-outstanding,exception-summary,payment-forecast,month-end-readiness}` | Date/filter-aware tenant reports, with CSV response when requested |

### Phase 2 endpoints implemented in this build

The implemented REST paths use the following concrete routes (all under `/api/v1/`):

| Method and path | Behavior |
| --- | --- |
| `GET,POST /invoice-intake-token` | Owner/finance reads or rotates the private tenant intake token |
| `POST /email-ingestion/{workspace_key}`; `GET /email-ingestion/logs` | Token-authenticated, message-id-idempotent multipart attachment ingestion and status history |
| `GET,POST /approval-rules`; `PATCH,DELETE /approval-rules/{id}` | Rule definitions; delete soft-deactivates |
| `GET,POST /approval-delegations`; `GET /approvals/pending`; `GET /invoices/{id}/approval-history` | Bounded delegation, current-user queue, step and decision history |
| `GET,POST /auto-approval-rules`; `PATCH /auto-approval-rules/{id}` | Owner-only, disabled-by-default rules with explicit vendor IDs and amount cap |
| `GET,POST /exception-slas`; `GET /exceptions/overdue`; `POST /exceptions/escalate-overdue` | Configure deadlines; escalation is explicitly triggered by owner/finance |
| `GET,POST /follow-ups`; `GET /invoices/{id}/follow-ups`; `PATCH /follow-ups/{id}` | Draft/edit and explicitly send vendor follow-ups |
| `GET,POST /custom-fields`; `GET,PATCH /invoices/{id}/custom-fields` | Invoice field definitions and typed values |
| `POST /bulk-jobs`; `GET /bulk-jobs/{id}`; `POST /bulk-jobs/{id}/commit` | Time-limited preview and commit for exception assignment/resolution |
| `GET /notifications`; `PATCH /notifications/{id}/read`; `GET,PATCH /notification-preferences` | Per-user in-app queue and preferences |
| `GET /reports/{name}?from=YYYY-MM-DD&to=YYYY-MM-DD`; `?export=csv` | Tenant-scoped live reports and CSV download |
| `PATCH /grns/{id}/service-acceptance` | Store/purchase/finance evidence for service matching |
| `PATCH /purchase-orders` with `action: "edit"` | Replace a draft PO's vendor/date/lines with a required reason and create the next immutable revision; submitted or approved POs cannot be edited |
| `GET /purchase-orders/{id}/revisions` | Tenant-scoped snapshots and change notes for the PO's revisions |

The initial design table above is the broader target contract; this concrete list reflects the shipped handlers. Provider-specific polling, scheduled escalation, and report snapshots are not configured.

## Phase 3 WhatsApp endpoints

Authenticated routes require tenant membership and `X-Workspace`. The Meta callback is public but verifies its GET challenge and POST HMAC signature.

| Method and path | Behavior |
| --- | --- |
| `GET /whatsapp/webhook` | Verify Meta callback challenge using the server-side verify token |
| `POST /whatsapp/webhook` | Verify `X-Hub-Signature-256`, ingest/deduplicate messages and invoice attachments, and apply outbound delivery states without downgrading delivered/read/failed messages on delayed callbacks |
| `GET,POST /whatsapp/endpoints` | List or connect a Meta phone-number ID to this tenant; owner/admin only to connect |
| `GET /whatsapp/messages` | Tenant-scoped message history, delivery states, and invoice references |
| `PATCH /whatsapp/messages/{id}` | Finance links an unassociated inbound message to an invoice in the same tenant |
| `GET,POST /whatsapp/drafts` | List or create approval/reminder/clarification drafts; recipient consent is required |
| `GET,POST /whatsapp/consents` | List tenant consent records or have Finance record verified opt-in/opt-out evidence; inbound STOP keywords revoke opt-in automatically |
| `POST /whatsapp/drafts/{id}/send` | Finance-only explicit send through the configured approved Meta utility template; a draft claim prevents concurrent double-send |
| `POST /whatsapp/drafts/{id}/reconcile` | Finance-only evidence-backed resolution of a send stuck in `SENDING` for at least five minutes; confirmed delivery requires the Meta message ID and never retries |

## Google Gmail connection

| Method and path | Behavior |
| --- | --- |
| `GET /google/gmail` | Finance/owner only; returns connection status, granted scopes, and account email without tokens |
| `POST /google/gmail` | Finance/owner only; creates a 10-minute one-time state and returns the Google authorization URL for Gmail read-only access |
| `POST /google/gmail/oauth/callback` | Public one-time code exchange guarded by the stored state; verifies Google's account identity and encrypts the offline refresh token at rest |
| `DELETE /google/gmail` | Finance/owner only; disconnects and erases the stored refresh token |

The configured callback is `http://localhost:3000/integrations/gmail/callback`. Gmail account connection is implemented; mailbox synchronization and attachment import from this connection are not yet enabled.

## Google sign-in

| Method and path | Behavior |
| --- | --- |
| `GET /auth/oauth/google/start?workspace={workspace_key}` | Public start for an existing workspace; validates the workspace and creates a 10-minute one-time state |
| `GET /auth/oauth/google/callback/` | Exchanges the authorization code, verifies Google's email identity, requires an existing active workspace membership, and redirects JWTs in the URL fragment to the local login page |

Google sign-in does not create accounts or workspace memberships. Use normal company signup for new accounts. The server uses the callback configured in `GOOGLE_SIGNIN_REDIRECT_URI` and the backend-only OAuth client file.

This is the first Phase 3 vertical slice. It does not yet implement one-time approver action links or scheduled reminders. Real outbound delivery requires Meta credentials and an approved one-placeholder template.

| Method and path | Purpose / access |
| --- | --- |
| `POST /auth/register-company` | Create tenant, owner user, membership; body `{company_name, workspace_key, name, email, password}` |
| `POST /auth/login` | Authenticate; body `{email,password}` |
| `POST /auth/logout` | Revoke session/token |
| `GET /auth/me` | Current user, memberships, active tenant, role |
| `POST /users/invite` | Owner invite; body `{email,role}` |
| `GET /users` | Tenant members; owner/admin access |
| `PATCH /users/{id}/role` | Change tenant membership role; owner only |
| `POST /vendors` | Create vendor |
| `GET /vendors` | Paginated/filterable vendor list |
| `PATCH /vendors/{id}` | Update vendor |
| `POST /invoices/upload` | Multipart `file` and optional metadata; creates invoice/document and queues extraction |
| `POST /invoices` | Manual invoice and lines creation; extraction not required |
| `GET /invoices` | Paginated; filters status, vendor, invoice date range, assigned/duplicate; ordering date, amount, created |
| `GET /invoices/{id}` | Invoice, lines, documents, latest extraction/match, exceptions, approvals |
| `PATCH /invoices/{id}` | Edit review fields/lines; increments version and audits changes |
| `POST /invoices/{id}/confirm-extraction` | Confirm current corrected version; queues or runs matching |
| `POST /invoices/{id}/submit-for-approval` | Submit eligible invoice version |
| `POST /invoices/{id}/approve` | Approver decision `{comments, invoice_version}` |
| `POST /invoices/{id}/reject` | Approver decision `{comments, invoice_version}` |
| `POST /invoices/{id}/export` | Queue eligible invoice for Tally CSV export |
| `POST /purchase-orders/import` | Multipart CSV upload; returns import job/row diagnostics |
| `GET /purchase-orders` | Paginated; filters vendor, status, unmatched, date range |
| `GET /purchase-orders/{id}` | Header and lines |
| `POST /grns/import` | Multipart CSV upload; returns import job/row diagnostics |
| `GET /grns` | Paginated; filters vendor, PO, status, unmatched, date range |
| `GET /grns/{id}` | Header and lines |
| `POST /matching/run` | Run matching for `{invoice_ids}` or eligible tenant queue |
| `GET /exceptions` | Paginated; filters status, vendor, code, severity, assignee, date range |
| `GET /exceptions/{id}` | Exception plus source comparisons |
| `POST /exceptions/{id}/assign` | `{assigned_to_id}`; allowed operational roles |
| `POST /exceptions/{id}/resolve` | `{resolution_note, override_reason?}`; override reason required for override action |
| `GET /dashboard/summary` | Counts, values, aging, monthly volume, exception breakdown |
| `GET /exports/tally-csv` | Download completed export artifact or select export by job ID |
| `GET /audit-logs` | Read-only paginated audit records with actor/action/object/date filters |

## Representative schemas

Invoice response:

```json
{
  "id": "uuid",
  "status": "REVIEW_REQUIRED",
  "version": 1,
  "vendor": {"id": "uuid", "name": "Example Components", "gstin": "..."},
  "invoice_number": "INV-001",
  "invoice_date": "2026-10-01",
  "due_date": "2026-10-31",
  "po_number": "PO-001",
  "lines": [],
  "totals": {"taxable": "1000.00", "gst": "180.00", "tds": "0.00", "total": "1180.00"},
  "extraction": {"status": "COMPLETED", "confidence": {"invoice_number": 0.98}},
  "match": {"outcome": "EXCEPTION", "blocking_exceptions": 1}
}
```

Upload returns `202 Accepted` with invoice ID, initial status, and extraction job state. Import returns accepted row count, rejected row count, and row-numbered validation messages. Async operations expose a job/status resource through their owning entity or import job endpoint.

## Filtering, authorization, and errors

Each endpoint has role/action checks. All nested resource references are verified in the same tenant. Unknown or cross-tenant IDs return 404. Invalid workflow transitions return 409; field validation returns 400 with field-level details. Rate-limit authentication and upload endpoints. Do not expose storage keys, provider credentials, raw internal stack traces, or another tenant’s existence.
# Phase 3 endpoints

- `GET/POST /api/v1/vendor-portal/invitations` lists invitations and creates a vendor-specific secure link. `PATCH /api/v1/vendor-portal/invitations/{id}` revokes it. The raw token is returned only on creation.
- `GET/POST /api/v1/vendor-portal/access/{token}` exposes only that vendor's invoice statuses, accepts validated invoice uploads, or accepts an invoice-specific question (`action: "message"`). `GET /api/v1/vendor-portal/access/{token}/invoices/{invoice_id}/messages` returns that invoice conversation. Uploads are capped at 12 MB and exact file checksums are deduplicated.
- Authenticated workspace responses are available at `GET/POST /api/v1/vendor-portal/invoices/{invoice_id}/messages`. This records a portal message; it does not send email or WhatsApp.
- `GET /api/v1/auth/workspaces` lists only the authenticated user's active workspace memberships. `X-Workspace` still selects one tenant and all data routes remain scoped to that tenant.
- `GET/PATCH /api/v1/ai-review/settings` reads/configures the tenant provider and opt-in (owner only). PATCH accepts `{provider: "openai"|"gemini", enabled: boolean}` with either field optional. The selected backend key must be present before enabling. `GET/POST/PATCH /api/v1/ai-review/suggestions` lists suggestions, creates them with `{invoice_id, confirm_external_processing: true}`, and stores a user's `ACCEPTED`/`DISMISSED` review decision. Provider keys and models are backend environment variables (`OPENAI_API_KEY`/`OPENAI_MODEL`, `GEMINI_API_KEY`/`GEMINI_MODEL`).
- `GET/POST /api/v1/api-keys` lists/creates keys (owner only); the raw key is returned once. `PATCH /api/v1/api-keys/{id}` revokes a key. Current scope is `invoices:read`; integrations call `GET /api/v1/external/invoices` with the API key as a Bearer token.
- `GET/POST/DELETE /api/v1/google/gmail` reads connection state, starts OAuth, or disconnects and erases the stored refresh token. `POST /api/v1/google/gmail/sync` reads up to 25 messages matching `newer_than:30d has:attachment`, imports supported PDF/image files into invoice review, and deduplicates by Gmail message ID. Finance/owner only; the integration uses Gmail read-only scope and does not change mailbox state.
- `GET /api/v1/bank-reconciliation?suggestions_for={transaction_id}` returns up to five tenant-scoped payment candidates with exact amount and date/reference evidence. Suggestions never create a match; `PATCH /api/v1/bank-reconciliation` with `action: "match"` remains a separate finance-user decision, followed by a separate `action: "reconcile"` confirmation.
- `PATCH /api/v1/matching/settings` accepts `over_receipt_tolerance_percent` from 0 to 100 (default 0). `GET /api/v1/purchase-orders` returns per-line ordered, received, remaining, and maximum receivable quantities. `POST /api/v1/grns` and `POST /api/v1/grns/import` enforce that cumulative receipts stay within the configured ceiling; imports report an over-limit row as rejected.
- `GET/POST /api/v1/tally-mappings` lists and upserts tenant-scoped voucher, vendor, category, GST-rate, TDS-section, and cost-center mappings. `PATCH/DELETE /api/v1/tally-mappings/{id}` updates or removes a mapping. Owner/finance only can mutate; export uses mappings and keeps the current balanced-voucher/payment-ready guards.
- `GET/POST /api/v1/webhooks` lists/creates subscriptions (owner only); the signing secret is returned once. `GET /api/v1/webhooks/{id}` returns recent delivery history, `PATCH` pauses/reactivates, and `POST /api/v1/webhooks/{id}/test` queues a test event if subscribed. Finance or owners can retry a failed delivery with `POST /api/v1/webhooks/deliveries/{delivery_id}/retry`, at most three times per event; the original event ID and payload are retained for receiver-side deduplication. Signatures use `X-KriyoPay-Signature-256: sha256=<HMAC-SHA256>` over the exact request body. Automatic delivery still requires the `deliver_webhooks` management command to run on a scheduler.

