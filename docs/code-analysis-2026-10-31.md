# KriyoPay code analysis — 31 October 2026

## Scope and assessment

Repository-wide architecture and risk review of the Next.js frontend, Django API, domain models, migrations, worker flows, integration boundaries, tests, and development/CI configuration. The inventory contains 481 Python/TypeScript/TSX/CSS files, approximately 39,753 lines including migrations and tests, and 79 frontend page routes. Generated assets, dependencies, credentials, and demo media are excluded from the code inventory.

This is a broad code review with deeper tracing of authentication, tenant permissions, invoice matching/approval/payment, public intake, reconciliation, fleet mutations, and configuration. It is not a claim that every line or every execution path has been independently verified. External providers and a live production deployment were not exercised. Application source changes were not made.

The application has substantial implemented workflows and useful financial safeguards. However, staff session security, inconsistent enforcement across entry points, broken configuration mutations, and failing backend checks prevent treating the current checkout as production-ready.

## Architecture and main flows

| Area | Implementation and responsibility |
| --- | --- |
| Web application | Next.js 14 App Router, React 18, TypeScript; MUI components/grids/charts alongside Tailwind and Radix wrappers. Most operational pages fetch API data in the browser. |
| API | Django 5, Django REST Framework, SimpleJWT, PostgreSQL for normal operation. Tenant records share tables and use explicit tenant filters. |
| Tenant access | `accounts/permissions.py` resolves membership using `X-Workspace`, enforces route/role and subscription rules. Branch scope currently blocks most workflows rather than filtering business data. |
| Invoice intake | File uploads, manual entry, email webhook, Gmail sync, WhatsApp, vendor portal and ERP review. Documents are stored separately and associated with invoices. |
| Invoice processing | Celery extraction → human review or automation checks → PO/GRN/vendor/duplicate matching → exception resolution → configured approval steps or explicit auto-approval → payment-ready state. |
| Supplier finance | Payment allocations reduce outstanding balances; credit/debit notes adjust payable amounts. Payout instructions are internal review records and do not transfer money. |
| Accounting | Reviewed Tally CSV/XML exports and provider adapters for Dynamics Finance, ERPNext and Zoho Books. ERP imports are staged/reviewed before local application. |
| Reconciliation | Bank statement imports, source-account provenance, exact amount/direction matching, saved candidates, revision/evidence checks, group allocation and review history. |
| Fleet | Vehicles/drivers/customers → transport orders → dispatch/trips/milestones → reviewed revenue/expenses → customer invoices/collections; separate driver earnings, salary, advance recovery and receipt workflows. Includes phone GPS, ETA, docks, return loads and exception monitoring. |
| Internal platform | Separate staff roles, company onboarding, plans/features, subscriptions, Razorpay checkout/refunds/webhooks, usage and audit views. |
| Background operations | Celery and Redis; beat schedules extraction/workflow recovery, Gmail intake, billing/ERP recovery and fleet notifications. Outbound tenant webhooks also have a management-command delivery path. |

Frontend `src/lib/api.ts` adds bearer/workspace headers, rotates refresh tokens, coalesces simultaneous reads and caches successful reads for two seconds. JWTs are stored in localStorage. Navigation visibility is supplementary; authorization must remain on the backend.

## Prioritized findings

### 1. High — MFA verification belongs to the account, not the current session

Locations: `backend/accounts/auth.py:5`, `backend/admin_console/permissions.py:20`, `:38`, `:48`; `backend/admin_console/auth.py:107`.

The ordinary `/auth/login` endpoint issues normal JWTs to staff after password authentication. `IsAdminStaff` accepts a privileged account when its shared `mfa_last_verified_at` is less than 24 hours old. It does not check that the presented JWT/session completed MFA. Consequently, after one legitimate MFA verification, a fresh password-only login can access staff APIs during that window. For SUPPORT/ADMIN staff with optional MFA enabled but not enforced, the permission does not require MFA at all even though the admin login serializer prompts for it.

Read-only runtime probes confirmed that the freshness predicate accepts a recently verified staff object without a request/token, and that optional MFA on SUPPORT does not trigger the permission requirement.

Fix: issue and enforce an MFA assurance claim tied to the current session, carry assurance safely through refresh, and apply one staff authentication policy to all token-issuing paths. Enrollment should use a narrowly scoped pending credential. Add cross-session and optional-MFA regression coverage.

### 2. High — public vendor links survive company deletion and bypass lifecycle restrictions

Locations: `backend/phase3/views.py:684`, `:706`; `backend/admin_console/views.py:143`.

Deleting a company disables its memberships and marks the tenant deleted. Vendor portal access validates only token hash, revocation and expiry; it does not reject a deleted or suspended tenant. An existing unexpired vendor link can therefore still list invoice details, read messages, submit messages and upload invoices after company deletion. Ordinary authenticated tenant requests use stronger restrictions. The shipment portal already demonstrates a better approach by checking tenant deletion and fleet availability.

Fix: centralize lifecycle validation for all public/background entry points and revoke public credentials on company closure. Test retained records remain inaccessible through every intake/portal channel.

### 3. High — feature-configuration mutation endpoints have incompatible arguments

Locations: `backend/admin_console/configuration.py:81`, `:222`, `:285`; `backend/admin_console/views_configuration.py:170`.

`set_feature_override` accepts `tenant_or_id`. Its callers pass either `tenant=` or `tenant_id=`, which raise `TypeError` before doing any database work. The single-update endpoint returns 500; bulk/create operations catch the exception and report per-item errors, potentially inside an apparent successful HTTP response.

Direct runtime calls reproduced both unexpected-keyword failures. This concerns the `/admin/configuration/...` API family; the older company-entitlements API is a separate implementation.

Fix: standardize the service signature and callers, exercise each routed mutation, bind the actor from the request and keep configuration history/audit behavior consistent across both API families.

### 4. High — external API keys bypass the ordinary subscription and branch policy

Locations: `backend/phase3/views.py:926`, `:936`; `backend/accounts/permissions.py:35`, `:111`.

API-key permission checks active membership and scope, and the external invoice endpoint checks the `api_access` feature. Neither enforces branch scope or suspended/churned subscription restrictions. Feature resolution itself does not disable features based on lifecycle status. An existing key can thus continue reading invoice data while the ordinary API denies the same membership, including when branch scope is enabled after key creation.

Fix: reuse a shared read-access policy across JWT, API key, public token and worker authentication. Test an existing key after suspension and branch-scope changes.

### 5. Medium — monthly invoice limits are enforced only at one request boundary

Locations: `backend/accounts/permissions.py:122`, `:154`; `backend/invoices/signals.py:11`; `backend/invoices/phase2_extended.py:73`; `backend/phase3/views.py:706`.

The invoice quota is checked for POST to the invoice collection. Alternate intake paths create Invoice objects directly and increment usage afterward without enforcing that limit. Concurrent ordinary uploads can also both observe the same available quota because quota checking and invoice creation are not serialized. Additionally, `limit_value or plan.invoice_limit` treats an explicit zero override as absent.

Fix: enforce quota in a shared transactionally protected invoice creation operation used by every intake channel; distinguish zero from an absent limit.

### 6. Medium — an owner can demote the last owner

Location: `backend/invoices/views.py:203`.

The role-change endpoint permits an OWNER to change their own membership to any valid role. It does not ensure another active owner remains. A single-owner company can lose all tenant-level user/branch administration and require platform intervention.

Fix: lock the relevant membership/tenant state and reject removal of the final active owner. Include simultaneous owner-demotion coverage.

### 7. Medium — trip editing does not preserve dispatch exclusivity under all changes

Locations: `backend/fleet/views.py:666`, `:1676`; `backend/fleet/serializers.py:287`.

Trip creation locks vehicle/driver records and prevents another DRAFT/IN_PROGRESS/SUBMITTED trip using either resource. Trip PATCH allows reassignment without those locks; serializer overlap checking runs only when both start and end timestamps exist and omits DRAFT from its overlap query. A draft trip with missing times can therefore be reassigned to a truck/driver already committed to another active trip. Concurrent PATCH/review operations can also race.

Fix: share assignment validation/locking between create and update, and serialize updates with trip lifecycle transitions.

### 8. Medium — concurrent Tally exports can export the same invoice twice

Location: `backend/exports_app/services.py:13`.

The service is atomic but validates caller-supplied invoice instances without reloading and locking them. Two requests can both load PAYMENT_READY invoices, pass validation, generate separate export jobs and mark the same invoices EXPORTED. Atomicity alone does not prevent stale reads.

Fix: reload and lock the selected invoice rows before validation; define an explicit replay/download policy so retries return an existing export where appropriate. PostgreSQL concurrency testing is needed.

### 9. Medium — outbound webhook workers do not claim deliveries atomically

Location: `backend/phase3/services.py:107`.

`deliver_due_webhooks` selects due rows and sends them without a claim token or row-lock transition. Overlapping command/scheduler instances can deliver the same event concurrently and overwrite attempt counters. Webhook receivers should expect at-least-once delivery, but overlapping workers should still preserve coherent attempts and retry state.

Fix: claim a bounded batch transactionally, send outside the transaction and finalize only for the matching claim. Preserve event IDs for receiver deduplication.

## Existing strengths

- Tenant filters and tenant-bound foreign-key serializer querysets are present in key workflows.
- Supplier payments share a service with invoice row locks, positive/exact decimal validation, allocation checks and idempotency conflict detection.
- Approved/payment-linked invoices have explicit edit locks; invoice decisions prevent submitter self-approval.
- Reconciliation verifies source account, currency, direction, amount, evidence freshness and duplicate claims, and records review events.
- ERP/webhook HTTP transports validate public destinations and pin the resolved address while preserving TLS hostname verification.
- API keys are hashed; portal credentials use high-entropy tokens stored as hashes; ERP/webhook secrets are encrypted.
- Worker flows include extraction claim/version checks and stalled-job recovery. Provider outcomes are not generally presented as simulated successful transfers.

## Maintainability and scaling observations

- `fleet/views.py` is 2,601 lines; `phase3/views.py` is 1,019. They mix HTTP concerns, orchestration, accounting rules, notifications and persistence. Split by domain use case as behavior is changed, preserving shared transactions and authorization.
- Several parallel configuration layers (`services.py`, `configuration.py`, manager/repository/controller/helper modules) resolve similar concepts. The incompatible mutation signature is a concrete symptom of drift.
- Several APIView list endpoints return complete collections or silently cap results at 100/200/500. DRF's global pagination does not paginate manually constructed Response objects. Growing tenants need server pagination/filtering rather than browser-only tables.
- Role and entitlement rules depend heavily on URL prefixes plus individual view checks. New routes can miss expected rules. Prefer explicit action policies reused across authentication mechanisms.
- Audit model instance methods reject updates/deletes, but this is application-level protection rather than database-enforced immutability; QuerySet operations and direct database access need separate controls if tamper resistance is required.
- Python dependency ranges are broad and have no resolved lockfile; CI uses `npm install` despite a package lock. Reproducible dependency installation and a production build check would improve release confidence.
- README has stale product-document paths and says staff two-factor authentication is incomplete while MFA implementation is present. Document the exact implemented assurance and limitations after repairs.

## Validation

Frontend type checking: passed. Frontend tests: 25 passed across 8 files. Lint: passed with one Next.js `<img>` warning in the MFA page. Production build: passed using a separate `.next-analysis` output directory; the build's automatic tsconfig include change was removed afterward.

Django system check: passed. Migration drift check: no changes detected. Deployment check with the local environment: five warnings for HSTS, SSL redirect, secure session/CSRF cookies and DEBUG. These describe the loaded local configuration and do not establish the settings of an unseen production host. The settings module also has an unsafe development SECRET_KEY fallback; production should fail closed without a configured secret.

Backend pytest final result: **20 failed, 220 passed, 9 skipped**, with no setup errors (221.60 seconds). The first sandbox run produced 32 temporary-directory setup errors; rerunning outside the sandbox resolved those environmental errors. Many admin and platform-settlement tests fail before their intended assertions because fixtures do not satisfy the new MFA gate; that is not evidence that each underlying checkout/refund/settlement workflow is defective. One MFA lifecycle test also expects a `mfa_verified` response field that the implementation does not return. Django's default test command discovered only 37 tests and reported 16 failures plus one error; pytest is necessary to include the repository's function-based tests.

Tests use `DJANGO_TEST_SQLITE=1`. SQLite cannot validate PostgreSQL row locking; concurrency findings above are static code-path findings requiring PostgreSQL regression coverage. No live Razorpay/Meta/Google/ERP requests or provider sandbox verification were performed as part of this review.

## Suggested implementation order

1. Repair session-bound staff MFA and add authentication regression coverage.
2. Unify lifecycle, branch and entitlement checks across API keys, public intake and workers.
3. Repair configuration endpoint/service contracts and align admin test fixtures and response contracts.
4. Centralize invoice quota enforcement, preserve the last owner, and fix fleet/export concurrency boundaries.
5. Make webhook claiming safe, add PostgreSQL concurrency checks, then improve pagination, dependency reproducibility and module structure.

Detailed command output is retained in `tmp/backend-analysis-tests.txt` and `tmp/frontend-analysis-build.txt`.
