# KriyoPay only

Decision: 6 November 2026. Reseller/white-label development and the independent-product phase plan are retired.

- One KriyoPay login at `/login`; no product selector or branding API dependency.
- Existing KriyoPay Super Admin, customer companies, subscriptions, feature pricing and company/branch permissions remain active.
- Default PostgreSQL backend, public business tables and ordinary scheduled jobs are used. HTTP headers, query parameters and reseller route prefixes cannot select another schema.
- Previous reseller sessions and queued jobs are explicitly refused so they cannot run against KriyoPay records.
- Reseller configuration/provisioning endpoints and commands are retired. Old frontend management URLs redirect to KriyoPay administration.
- The retired reseller schema, registry entry, accounts, company/demo records, stored files and local onboarding credentials were deleted on explicit user request. KriyoPay public company/user/invoice/trip counts were verified unchanged. No reseller data was merged into KriyoPay.
- The `partners` app remains installed for applied migration compatibility and small fixed-identity/session-rejection helpers. It no longer provides active reseller routing or administration.

Deployment: restart the API, Celery workers and Beat together. Do not run old reseller workers or beat schedules against the active KriyoPay database. Existing KriyoPay accounts retain their passwords. The former reseller schema was permanently dropped separately on explicit user request.
