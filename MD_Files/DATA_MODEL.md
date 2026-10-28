# KriyoPay Data Model

## Conventions

- PostgreSQL 18, Django-managed migrations, UUID primary keys (`uuid4`), UTC timestamps, `created_at` and `updated_at` where mutable records exist.
- Every tenant-owned table carries a non-null `tenant_id` FK. Child rows repeat tenant_id for direct scoped lookup and enforce same-tenant parent relationships in service validation and, where practical, composite uniqueness/FKs.
- Monetary values use fixed precision `NUMERIC(18,2)` or higher where tax precision requires it; quantities/rates use `NUMERIC(18,6)`. Currency defaults to INR and is not user-selectable in MVP.
- Audit rows are append-only. Invoice corrections create versions/snapshots; extraction and matching results are append-only/versioned.

## Tables

## Phase 2 schema additions

These are additive tenant-scoped entities; implementation status is tracked in `CHANGELOG.md`. Every table uses UUID keys and a tenant FK. Child references must be checked against the same tenant in the service layer.

| Table | Key fields | Constraints and notes |
| --- | --- | --- |
| `email_ingestion_logs` | tenant_id, provider, message_id, sender, recipient, subject, status, attachment_results JSONB, retry_count, error | unique `(tenant_id,provider,message_id)`; intake token is tenant-owned; files enter normal document/invoice records |
| `vendor_aliases` | tenant_id, vendor_id, alias, normalized_alias, kind | unique `(tenant_id,normalized_alias,kind)`; kind is NAME/GSTIN/EMAIL_DOMAIN |
| `duplicate_checks` | tenant_id, invoice_id, candidate_invoice_id, kind, score, reasons JSONB, decision, decision_note, decided_by, decided_at | unique candidate and kind; kinds include FILE/EXACT/NEAR |
| `approval_rules` | tenant_id, name, priority, condition JSONB, steps JSONB, active, created_by, updated_by | validated rule schema; deterministic priority; no arbitrary executable expressions |
| `approval_steps` | tenant_id, invoice_id, sequence, approver_role/user, status, decision, comments, due_at, decided_at | ordered unique sequence per invoice/workflow; maker-checker and tenant membership constraints |
| `approval_delegations` | tenant_id, delegator, delegate, starts_at, ends_at, active | date range constraint; delegate must have suitable active tenant membership |
| `exception_slas` | tenant_id, exception_code, due_after_hours, priority, escalation_roles | unique tenant/code; active rules apply due dates on exception creation |
| `exception_escalations` | tenant_id, exception_id, level, escalated_to, reason, created_at | append-only history; unique exception/level where suitable |
| `vendor_follow_ups` | tenant_id, invoice_id, recipient, subject, body, status, created_by, sent_by, sent_at | outbound send requires an explicit authenticated action |
| `payments` / `payment_allocations` | tenant_id, vendor_id, reference, mode, paid_at, amount, invoice_id, allocated_amount | positive values, tenant/vendor consistency, total allocations bounded by net payable policy |
| `credit_notes` / `debit_notes` | tenant_id, invoice_id, grn_id, amount, reason, status, approved_by | pending notes do not change outstanding; approved notes are audited |
| `custom_field_definitions` / `invoice_custom_field_values` | tenant_id, invoice_id, key, field_type, required, options JSONB, value JSONB | unique tenant/key and tenant/invoice/definition; type-checked; required values checked before approval |
| `bulk_jobs` | tenant_id, operation, status, created_by, target_ids JSONB, preview JSONB, preview_token, expires_at, result JSONB | preview expires after 15 minutes; revalidates records before commit; per-record audit entries |
| `notifications` / `notification_preferences` | tenant_id, recipient, channel, status, payload JSONB, read_at; preference JSONB | no secrets/document bytes in notification metadata |
| `report_snapshots` | not implemented | Reports are currently generated from tenant-scoped live queries; snapshots are future work |

Required Phase 2 indexes include `(tenant_id,status)`, `(tenant_id,vendor_id,status)`, `(tenant_id,due_date)`, `(tenant_id,exception_code,status)`, and `(tenant_id,invoice_id,created_at)` on payment/approval histories. Use checks for positive payment/note amounts and allowed state combinations; retain all historical rows and reverse via explicit state transitions.

| Table | Key fields | Constraints and notes |
| --- | --- | --- |
| `tenants` | id, name, workspace_key, status, settings JSONB | unique `workspace_key`; settings hold validated tenant tolerances and export configuration |
| `users` | id, email, password hash, name, is_active | unique normalized email; Django user model |
| `memberships` | id, tenant_id, user_id, role, status | unique `(tenant_id,user_id)`; role enum; tenant FK |
| `invitations` | id, tenant_id, email, role, token_hash, expires_at, accepted_at, invited_by_id | unique active token hash; expiry/single-use checks |
| `vendors` | id, tenant_id, name, gstin, external_code, approved, terms JSONB | unique `(tenant_id,gstin)` when GSTIN present; indexed name/code |
| `purchase_orders` | id, tenant_id, vendor_id, number, order_date, status, source_ref | unique `(tenant_id,number)`; index tenant + number |
| `purchase_order_lines` | id, tenant_id, purchase_order_id, line_no, item_code, description, hsn_sac, quantity, uom, rate, taxable_value, gst_rate, gst_amount | unique `(tenant_id,purchase_order_id,line_no)`; quantity nonnegative |
| `grns` | id, tenant_id, vendor_id, purchase_order_id, number, received_at, status, source_ref | unique `(tenant_id,number)`; index tenant + number |
| `grn_lines` | id, tenant_id, grn_id, purchase_order_line_id, item_code, description, quantity_received, uom | same-tenant PO-line link; nonnegative quantity |
| `invoices` | id, tenant_id, vendor_id, invoice_number, invoice_date, due_date, po_number, status, currency, totals, current_version, uploaded_by_id | index `(tenant_id,invoice_number)`, `(tenant_id,vendor_id,invoice_number)`, `(tenant_id,status)`; invoice number is not globally unique because vendors may reuse numbers |
| `invoice_lines` | id, tenant_id, invoice_id, line_no, item_code, description, hsn_sac, quantity, uom, rate, taxable_value, gst_rate, gst_amount, tds_amount | unique `(tenant_id,invoice_id,line_no)`; nonnegative amount checks |
| `documents` | id, tenant_id, invoice_id nullable, storage_key, filename, media_type, size_bytes, checksum_sha256, source, uploaded_by_id, created_at | index tenant + checksum; duplicate candidates detected per tenant; storage key unique |
| `extraction_results` | id, tenant_id, invoice_id, document_id, provider, schema_version, output JSONB, confidence JSONB, status, created_at | immutable result; index invoice + created_at |
| `match_results` | id, tenant_id, invoice_id, run_number, rules_version, outcome, details JSONB, created_by_id, created_at | unique `(tenant_id,invoice_id,run_number)`; stores variances and linked source IDs |
| `exceptions` | id, tenant_id, invoice_id, match_result_id, code, severity, status, assigned_to_id, details JSONB, resolution_note, override_reason, resolved_by_id, resolved_at | indexes tenant + status, tenant + code, assignee + status; retained after resolution |
| `approvals` | id, tenant_id, invoice_id, invoice_version, approver_id, decision, comments, decided_at, ip_address, user_agent | one decision per approver/version as workflow policy allows; immutable decisions |
| `audit_logs` | id, tenant_id, actor_id nullable, action, object_type, object_id, before JSONB, after JSONB, metadata JSONB, request_id, created_at | append-only; indexes tenant + created_at, object, actor |
| `export_jobs` | id, tenant_id, status, format, requested_by_id, storage_key, row_count, debit_total, credit_total, error JSONB, created_at, completed_at | totals must balance for completed export; status transition validation |
| `notifications` | id, tenant_id, recipient_id nullable, channel, template, status, payload JSONB, provider_ref, sent_at, error JSONB | avoid storing unnecessary document contents or secrets |

## Phase 3 additions

| Entity | Key fields and constraints |
| --- | --- |
| `whatsapp_consents` | tenant, international phone, current opt-in state, evidence note, source, actor; unique `(tenant,phone)`; inbound opt-out messages update the record and append an audit event |
| `gmail_connections` | one connection per tenant, Google subject/email, encrypted refresh token, granted scopes, active state, connecting user; disconnect erases the stored token |
| `gmail_oauth_states` | tenant/user, hashed single-use state, expiry/consumption timestamps; never stores the raw state value |
| `google_signin_states` | workspace, hashed single-use state, expiry/consumption timestamps; callback issues JWT only after verified email and active workspace membership |
| `month_end_checklist` | tenant, YYYY-MM period, checklist key, review status/note/actor; unique `(tenant,period,item_key)` |

## Indexes

Required indexes: `(tenant_id, invoice_number)`, `(tenant_id, vendor_id, invoice_number)`, `(tenant_id, status)` for invoice status, `(tenant_id, status)` for exception status, `(tenant_id, number)` for PO number and GRN number. Add indexes for common joins/FKs, pending approvals, checksum lookups, and chronological audit queries. Use partial unique indexes for non-null GSTIN and active invitation token as appropriate.

## Constraints and state transitions

- Use `CHECK` constraints for nonnegative quantities, monetary values where valid, GST rate bounds, and valid enum values where Django/PostgreSQL supports them.
- Use unique constraints for tenant-scoped workspace keys, PO/GRN numbers, line numbers, and membership pairs.
- Enforce invoice/exception/export transition maps in transactional services; PostgreSQL constraints cannot conveniently express cross-row workflows. Add database checks for locally expressible invariants and cover transition services with tests.
- Prevent completed export records with unequal debit/credit totals via a database check or transactional validation plus constraint-compatible nullable status design.
- Audit log model denies update/delete in application/admin paths; production DB role should be insert/read only for audit table where feasible.

## Tenant relationship integrity

All tenant-owned objects carry `tenant_id`. Service methods load parents by `(tenant_id,id)` and reject cross-tenant references. Use composite uniqueness on `(tenant_id,id)` where needed to support composite FKs guaranteeing child-parent tenant agreement. Never cascade-delete audit records. Tenant lifecycle uses suspension/retention workflows rather than broad destructive cascades.

## Migration plan

1. Create tenant and custom user foundations before dependent apps.
2. Add memberships/invitations and vendors/procurement tables.
3. Add invoices, lines, documents, and extraction/matching result tables.
4. Add exceptions, approvals, audit, notifications, and exports.
5. Add indexes and constraints in separate migrations for safe deployment; backfill tenant identifiers before making any existing column non-null if migrating legacy records.
6. Run migrations in CI and release deployment; backup before production schema changes. Prefer additive migrations, then separately remove obsolete columns after application rollout.
