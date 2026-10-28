# Admin Data Model

- `AdminStaff`: user, internal role, active flag.
- `Plan`, `Feature`, `PlanFeature`, `TenantFeatureOverride`: configurable catalog and entitlements.
- `Subscription`: tenant, plan, lifecycle/billing dates and cycle.
- `TenantUsage`: tenant, period, metric, count, limit snapshot.
- `Payment`, `BillingInvoice`: internal payment and receivable history.
- `RazorpayWebhookEvent`: unique provider event ID, signed event payload, retry status, and processing error.
- `AdminAuditLog`: append-only actor, action, tenant, object reference, reason, metadata, timestamp.

Tenant business data remains in existing tenant models. Internal role rows are independent from tenant memberships.
