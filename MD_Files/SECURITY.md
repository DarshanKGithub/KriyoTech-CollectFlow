# Security Controls

## Authentication and authorization

Django accounts use Django password hashing and JWT access/refresh tokens. Production secrets and provider credentials belong in environment injection or a secret manager. Enforce short access-token lifetime, refresh rotation/revocation, HTTPS, secure HttpOnly cookie storage if cookies are selected, CSRF protection for cookie-authenticated mutations, and rate limits on authentication and upload endpoints.

Membership roles are tenant-scoped. Every API object lookup filters by the authenticated membership tenant; caller-supplied workspace headers only select among memberships the user already has. Auditors are read-only. Approval, override, role changes, and export require explicit server-side authorization.

## Tenant isolation and documents

Business tables carry tenant foreign keys. Object storage keys include tenant and opaque document IDs; downloads require authorization and short-lived URLs. Validate extension, MIME, content, size, and checksum; scan uploads in production. Do not expose storage keys or another tenant's existence. Keep tenant-isolation tests for every endpoint and background task.

## Financial and personal data

Collect the minimum user and invoice data required. Restrict GSTIN and source documents to tenant members. Use TLS in transit and encryption at rest for database volumes, object storage, and backups. Avoid invoice content, tokens, and secrets in logs. Define retention and deletion policy with customers before production.

## Audit controls

Record uploads, extraction results/corrections, imports, matching, exception assignment/resolution/override, approval decisions, exports, invitations, and role changes. Audit data is append-only in application code; production database permissions should prevent updates/deletes. Include actor, tenant, object, timestamp, request/job ID, and minimal metadata.

## Operational baseline

Patch dependencies, use least-privilege database/object-store identities, back up and test restore, rotate secrets, monitor failed login/job rates, and document incident response. Production security review is required before processing real financial documents.

## Phase 2 automation controls

- The implemented inbound webhook uses an unguessable per-tenant intake token in `X-Invoice-Intake-Token`, constant-time comparison, workspace-key routing, message-ID idempotency, attachment type/size checks, and checksum duplicate checks. Provider-specific signature/timestamp verification and external secret storage should be added when connecting a real email provider.
- Treat vendor aliases, approval rules, custom fields, and notification payloads as untrusted tenant input. Validate schemas, lengths, enum values, limits, and tenant ownership; never execute rule JSON as code.
- Only owner/finance roles may manage auto-approval, payment policy, rule definitions, payment records, or note approvals. Maker-checker and approver delegation are enforced on the server and constrained to active same-tenant memberships/date ranges.
- Auto-approval defaults off and requires deterministic persisted eligibility evaluation; it cannot clear duplicate/blocking exceptions or replace a required human approval. Every automated state transition records the rule version and evaluation details.
- Bulk preview tokens bind tenant, action, selected IDs, and expiry. Revalidate membership and record state at execution; the current synchronous exception actions are per-record audited. Add user binding/background-job monitoring when expanding bulk processing.
- Payment allocations and approved credit/debit notes use database transactions and constraints. Do not silently mutate or delete historical financial entries; use reversal/adjustment records with reason and actor.
- Vendor messages remain drafts until an authenticated user reviews and confirms sending. Inbound email content and invoice attachments are untrusted data and must not be treated as executable instructions.
- Reports, custom-field filters, and exports are tenant-scoped and permission-checked; notification and report artifacts contain only the minimum financial data needed.

## Phase 3 WhatsApp controls

- Meta webhook GET verification uses a backend-only verify token; POST events require constant-time HMAC-SHA256 signature validation against the raw request body and Meta app secret.
- Access token, app secret, verify token, Graph API version, and approved template are read only from backend environment/secret management; never accept credentials from the browser or webhook payload.
- Bind Meta phone-number IDs uniquely to a tenant. Deduplicate external message IDs per tenant, cap downloaded attachment bytes, allow only invoice MIME types, and keep provider URLs restricted to Meta media hosts.
- Require explicit recorded recipient consent and a finance-user send action for every outbound message. Preserve draft, actor, delivery status, invoice link, and audit event. Do not auto-send AI output or expose a public approval action link until one-time, expiry, approver-binding, and replay protections are implemented.
- Minimize conversation retention and avoid storing full provider webhook payloads, access tokens, or unnecessary contact data.
# Phase 3 integration key handling

- API keys are displayed once and stored as password hashes. Revoke a leaked key immediately; keys currently have invoice-read scope only.
- Webhook signing secrets are displayed once and encrypted at rest with `WEBHOOK_FERNET_KEY`. Back up that key securely; rotating or losing it prevents existing endpoint signatures from being generated.
- Webhook targets must use HTTPS on port 443 and resolve to public IP addresses. Delivery pins a validated public address, preserves TLS hostname verification, and does not follow redirects. Receivers should verify the HMAC header and deduplicate by event ID.
- AI review is disabled by default per tenant, owner-enabled, and requires explicit per-invoice confirmation. It sends invoice metadata and line fields to the configured provider; it does not upload the source file. The workspace must authorize that processing.
- Vendor portal links are bearer credentials; they are hashed at rest, expire, can be revoked, and are not emailed by the app. Share them through an approved channel.
- Google OAuth client JSON files are stored under the ignored `Google_Keys/` directory and referenced by backend-only file paths in `.env`. Never expose client secrets to Next.js/browser code or commit the JSON files. Google sign-in state is hashed, expires after ten minutes, and is single use; it only authenticates existing active workspace members. Gmail requests read-only scope, verifies the Google account, and encrypts its refresh token with `WEBHOOK_FERNET_KEY`. Disconnect erases KriyoPay's stored refresh token; the user can also revoke the grant in Google Account settings.
- Gmail sync is an explicit finance/owner action, reads at most 25 matching messages from the last 30 days, and never modifies message state. Attachment import accepts only PDF/PNG/JPEG/HEIC/HEIF, caps files at 25 MB, messages at 20 attachments/100 MB, and records idempotency by tenant plus Gmail message ID. Treat message headers and attachments as untrusted data; invoice files remain in the normal review queue.
- Bank payment suggestions are tenant-scoped, read-only hints. They require exact amounts, do not mark or reconcile transactions, and are followed by explicit finance-user match and reconcile actions.
- GRN creation and import serialize on the approved PO row and enforce cumulative per-line receipt ceilings. Over-receipt tolerance is finance-configured, audited, and defaults to zero; imported rows cannot bypass the same ceiling.
- Tally mappings are workspace-scoped and only owner/finance members can mutate them. Vendor mapping references are validated against that workspace; exports use the saved mapping snapshot for that generation and do not post entries to a customer's Tally company.
