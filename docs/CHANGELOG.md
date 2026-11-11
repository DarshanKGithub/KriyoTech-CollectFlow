# Changelog

## Phase 3 access and admin onboarding
- Added branch directory, activation controls, tenant-scoped member assignments, and audit events; branch-level filtering on business records remains pending.
- Added a first-run Super Admin bootstrap command that generates a random password once and refuses to create another active bootstrap Super Admin.
- Disabled public company self-signup. Internal admins onboard companies, choose plans/features, and invite owners; workspace login now discovers company memberships after email/password authentication.
- Redesigned tenant and internal staff sign-in screens and directed admin-console authentication failures back to the staff login.
- Verified 49 Phase 3/admin tests, Django system/migration checks, and a Next.js production build.

## Admin control plane (MVP)
- Added isolated staff authentication/roles, onboarding with expiring owner invitation links, plan and feature management, tenant overrides, subscriptions, usage tracking and limits, lifecycle access enforcement, admin audit views, and separate admin UI.
- Added tenant billing screens, server-created Razorpay Orders, signature and captured-state verification, signed idempotent webhook processing with Celery retries, and paid billing receipts.
- Seeded the initial configurable subscription plans and feature catalog in local PostgreSQL.
- Remaining: mandatory staff 2FA, lifecycle scheduler, impersonation, AI/storage usage counters, branch-level row filtering, and comprehensive production billing hardening.
