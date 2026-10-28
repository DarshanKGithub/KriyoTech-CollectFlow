# KriyoPay Admin Panel PRD

## Goal
Provide a separate internal control plane for KriyoPay staff to onboard companies, manage configurable plans and entitlements, inspect subscription and usage state, and audit support and billing actions.

## Audiences and access
Internal roles are `SUPER_ADMIN`, `ADMIN`, `SUPPORT`, `BILLING_ADMIN`, and `READ_ONLY`. Tenant roles stay separate. Every admin API requires an active internal staff record; tenant membership alone never grants access. The UI lives under `/admin-console` and has its own layout.

## MVP scope
- Internal dashboard and searchable company directory.
- Company onboarding creates a tenant, owner account/membership, trial or payment-due lifecycle, subscription, and audit entry.
- Internal admins choose the plan and feature entitlements before owner access is activated. Public company self-signup is disabled.
- First-run Super Admin is created only through a local operator command with a generated one-time password; tenant users cannot self-provision staff access.
- Configurable plans, feature catalog, plan entitlements, tenant overrides, lifecycle status, subscription and usage views.
- Billing/payment records and Razorpay integration status. Payment activation requires verified server-side evidence.
- Immutable append-only audit history for control-plane changes.

## Lifecycle
Companies move through `ONBOARDING`, `TRIAL`, `ACTIVE`, `PAST_DUE`, `GRACE_PERIOD`, `SUSPENDED`, `CANCELLED`, and `CHURNED`. Restriction behavior must be enforced by backend services. Existing tenant access is preserved until lifecycle enforcement is explicitly enabled and migrated.

## Success criteria
Staff can create a company and owner membership; define plans and features; see usage and account health; and review who changed what. Tenant users cannot call internal APIs. No frontend callback can mark a payment paid.

## Delivered MVP and deferred integrations
The initial control plane supports staff roles, company onboarding and owner invitations, configurable plans/features, tenant overrides, lifecycle management, usage snapshots and invoice enforcement, tenant Billing & Plan UI, Razorpay Orders/Checkout verification, signed idempotent webhook queue processing, internal billing receipts, refunds/offline payments, and audit views. Staff 2FA, automated lifecycle jobs, impersonation, storage/AI/API usage counters, formal email verification, and full onboarding automation remain incomplete. No simulated payment or secret exposure is allowed.
