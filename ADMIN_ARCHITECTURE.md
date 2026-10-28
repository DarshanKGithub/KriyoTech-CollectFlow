# Admin Architecture

The control plane is an independent Django `admin_console` app and Next.js `/admin-console` route group. Existing tenant authentication issues JWTs; internal APIs additionally require an active `AdminStaff` row. Staff roles and permissions do not derive from `is_staff`, tenant role, or workspace headers.

All company objects are keyed to `Tenant`; subscription, usage, plan entitlements, overrides, payments, and billing invoices are server-side records. A single entitlement service resolves plan defaults and non-expired tenant overrides. Admin mutations run in transactions and append an audit record. Razorpay webhooks will have a separate unauthenticated signature-verified endpoint.

MVP uses the existing PostgreSQL database and Django API. No Docker dependency. Next frontend uses a distinct admin shell and API prefix. Background renewal and webhook processing are deferred until Celery/Redis configuration exists.
