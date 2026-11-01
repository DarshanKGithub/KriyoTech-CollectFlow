# KriyoPay

KriyoPay is an invoice-to-payment control tower for Indian SMEs. It checks supplier invoices against purchase orders and goods receipts, routes exceptions and approvals, and generates a Tally-ready CSV. The ERP integration workspace now supports reviewed Tally accounting XML exports and posting, plus Dynamics 365 Finance, ERPNext and Zoho Books adapters. Customer connection and accounting mappings are required; see docs/erp-integrations.md for implemented capabilities and remaining production work.

## Local development

Requirements: Python 3.12, Node.js 20+, PostgreSQL 18, and (for background workers) a local Redis service. Start your installed PostgreSQL 18 service. This setup runs directly on the host without Docker. Create a PostgreSQL role and database, then copy `.env.example` to `.env` and update local credentials:

Once backend/frontend dependencies and PostgreSQL are ready, start the local stack with one PowerShell command from the repository root:

```powershell
.\start-dev.ps1
```

The script starts or reuses Redis (through the existing `kriyopay-redis` Docker container when needed), Django, Celery, and Next.js. Logs and managed process IDs are written under `.dev-runtime/`. Stop Django, Celery, and Next.js with `.\stop-dev.ps1`; Redis stays running. Docker Desktop must be running if Redis is not already reachable on port 6379. For manual startup, follow the commands below.

```powershell
psql -U postgres -c "CREATE ROLE kriyopay LOGIN PASSWORD 'kriyopay-local';"
psql -U postgres -c "CREATE DATABASE kriyopay OWNER kriyopay;"
Copy-Item .env.example .env
Set-Location backend
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

In a second PowerShell window, run the frontend:

```powershell
Set-Location Frontend
npm ci
npm run dev
```

The Next.js UI is at `http://localhost:3000`, Django API at `http://localhost:8000/api/v1/`, and Django admin at `/admin/`. Companies are onboarded by internal staff from `/admin-console`; public self-service workspace creation is disabled. The signup route explains this invitation-based flow. `python manage.py seed_demo` is an optional command for a disposable sample workspace only and should not be run for a real workspace.

The one-command `start-dev.ps1` checks `/api/v1/health` before reusing a backend port. If another application owns port 8000, it selects an available port from 8001–8010 and writes the selected public API URL to `Frontend/.env.local`. Next development mode reloads that file automatically. For manual Django startup, use the selected port (for example `python manage.py runserver 127.0.0.1:8001`). An explicit port can be selected with `./start-dev.ps1 -BackendPort 8001`; occupied ports belonging to other applications are rejected. A production frontend must be rebuilt after changing its public API URL.

The project is organized into two application folders: `backend/` contains Django, its domain apps, migrations, and Python dependencies; `Frontend/` contains the Next.js app and its npm configuration. Product and operational documents stay in the repository root.

The compliance area includes line-level tax arithmetic flags and an auditable month-end review checklist. These are operational checks only and do not verify GST registration with a government service or provide a statutory filing.

The transport fleet module is available at `/fleet`: tenant-scoped trucks, drivers, customers, transport orders, dispatch and trip milestones, delivery proof, reviewed trip costs, customer invoices and collections, effective-dated per-trip/per-kilometre driver pay policies, trip earnings, salary settlements, advance recovery, independent review, private receipt upload, follow-ups, and operational reports. Customer receivables remain separate from supplier payables. Apply Django migrations before using the module.

Purchase order goods receipts support cumulative partial deliveries. Over-receipt tolerance is set in workspace matching controls (default zero); the UI shows ordered, received, remaining, and maximum receivable quantities, and both manual GRNs and CSV imports enforce the configured limit.

Tally export ledger names can be configured at `/exports/settings` for vendors, purchase categories, GST rates, TDS sections, and cost centers. The CSV export remains a reviewed data interchange file; connecting a customer Tally instance or validating ledgers still requires their accountant and local Tally setup.

Obtain a tenant token at `POST /api/v1/auth/login` with email and password. The frontend then discovers active company memberships via `GET /api/v1/auth/workspaces`; send `Authorization: Bearer <access>` and `X-Workspace: <workspace_key>` on tenant-scoped requests. A company owner can manage the branch directory and branch assignments at `/branches` and `/branch-assignments`; branch filtering on business records is still in progress.

## Services

- `Frontend/`: Next.js App Router, TypeScript, Tailwind.
- `backend/`: Django 5 and DRF API.
- PostgreSQL 18: local database service.
- Redis: local background-job broker when running Celery workers.

## Configuration and files

All secrets use environment variables. `.env` is ignored by Git. Local uploads use Django media storage; production should configure S3-compatible private storage. Invoice extraction supports manual entry and Gemini. To enable automatic extraction when a document invoice arrives, set `EXTRACTION_PROVIDER=gemini`, `GEMINI_API_KEY`, and `GEMINI_MODEL` in `.env`, start Redis, and keep a Celery worker running from `backend` with `python -m celery -A config worker -P solo -l info`. The UI queues extraction after uploads and supported email, Gmail, WhatsApp, and vendor-portal intake; extracted values remain in review for a person to check. If the provider or queue fails, the invoice remains available for manual review or extraction retry.

The `Google_Keys/` directory is also ignored by Git. The Gmail connector reads the OAuth client JSON named by `GOOGLE_GMAIL_CLIENT_FILE` on the backend only; its registered redirect URI must exactly match `GOOGLE_GMAIL_REDIRECT_URI`. `/integrations` can sync up to 25 messages matching `newer_than:30d has:attachment`; supported invoice attachments enter normal review and duplicate checks. Gmail access is read-only and the sync does not mark messages read or change labels. The separate `GOOGLE_SIGNIN_CLIENT_FILE` supports existing-account sign-in; its callback must exactly match `GOOGLE_SIGNIN_REDIRECT_URI`. Client secrets remain in the ignored JSON files and are never bundled into the frontend.

## Product documents

See `UX.md`, `Plan.md`, `PHASE3_PLAN.md`, `Architecture.md`, `PRD.md`, `DATA_MODEL.md`, `API_SPEC.md`, `MATCHING_RULES.md`, `TALLY_EXPORT_SPEC.md`, `ONBOARDING.md`, `SECURITY.md`, `OPERATIONS.md`, and `TEST_PLAN.md`.
# Phase 3 operational pages

The current Phase 3 increment adds `/compliance` for human-reviewed invoice tax data, `/bank-reconciliation` for mapped CSV/XLSX statements, multi-line and revisioned PO drafts, PO approval/GRN quality actions, vendor portal submission/status/questions and workspace replies, workspace switching, opt-in OpenAI/Gemini invoice suggestions, hashed read-only API keys, and signed webhook outbox delivery with bounded retries. Owners/finance can review recent webhook deliveries and manually retry failed events up to three cycles; automatic delivery still requires an operator-scheduled worker. These use tenant-scoped APIs and require migrations. PostgreSQL 18 is configured in `.env` and migrations are applied to the local database. Set `DJANGO_TEST_SQLITE=1` only for local tests; normal runs use PostgreSQL. Compliance checks are format/arithmetic screening only. Bank reconciliation currently supports CSV/XLSX and exact amount matching only. Portal links are not emailed; copy them to the intended vendor and treat them as credentials. AI requires owner provider selection and enablement, plus per-request consent; it sends invoice metadata but not the source document. A development `WEBHOOK_FERNET_KEY` is stored in ignored `.env`; production must use its own managed secret. Schedule `python manage.py deliver_webhooks` for automatic delivery and retries.

# Internal admin control plane

KriyoPay has a separate internal staff area at `/admin-console` and `/admin-login`. Tenant membership does not grant access. Bootstrap the first Super Admin once on a new local install. The command generates a high-entropy password and prints it once; store it in a password manager and rotate it after the first sign-in:

```powershell
cd backend
python manage.py migrate
python manage.py seed_admin_catalog
python manage.py bootstrap_super_admin admin@your-company.example
```

The bootstrap command refuses to create a second active Super Admin. Available roles: `SUPER_ADMIN`, `ADMIN`, `SUPPORT`, `BILLING_ADMIN`, and `READ_ONLY`. To add an internal role to an existing account, use `python manage.py provision_admin_staff existing@company.example SUPPORT`. Provisioning and all console mutations are recorded in the append-only admin audit log. Never provision staff from a public self-service request.

Company onboarding creates the workspace, owner membership, trial/onboarding subscription, and seven-day one-time password setup invitation. Configure the Django email backend before treating the invitation as delivered. Plans use integer paise amounts; run `seed_admin_catalog` to create the initial editable plan and feature catalog.

The control plane supports company onboarding and owner invitations, plan/feature configuration, tenant entitlement overrides, lifecycle status updates, monthly invoice/user limits, usage/payment/audit views, tenant Billing & Plan, Razorpay Orders and Checkout, server-side payment verification, and signed idempotent webhook processing through Celery. Offline payment recording and refund initiation are present; refunds require Razorpay configuration and a verified outcome webhook. For local webhook processing, run `python -m celery -A config worker -P solo -l info` from `backend` after starting Redis; production should run a managed Celery worker. Razorpay requires all three server-side keys and a publicly reachable HTTPS webhook endpoint. Staff two-factor authentication, impersonation, scheduled renewal/grace jobs, AI/storage usage limits, and branch-level filtering on invoices, vendors, POs, GRNs and payments remain incomplete. Branch directory and member assignments are currently administrative metadata only. The UI never simulates payment success. Do not expose this MVP as a production-ready billing admin until the remaining security-sensitive integrations are complete.

Verification:

```powershell
python manage.py check
python manage.py test admin_console
```

## ERP and accounting integrations

Open `/integrations/erp` for Microsoft Dynamics 365 Finance, ERPNext, TallyPrime and Zoho Books connections, import reviews, export snapshots and reconciliation. Read [ERP integration architecture and setup](docs/erp-integrations.md) before connecting an accounting system. Full production two-way operation still requires customer sandbox verification and the provider-specific work listed there.

## Advanced transport platform roadmap

The proposed expansion covers tracking history/geofences, multi-stop dispatch, fuel and maintenance, transport billing, customer/driver apps, AI assistance, Indian transport integrations, and later warehouse and load-marketplace modules. These documents describe planned work and distinguish it from existing code:

- [Transport platform architecture](docs/transport-platform-architecture.md)
- [Phased build plan, backlog and acceptance gates](docs/transport-platform-build-plan.md)
- [Repository analysis and prerequisite fixes](docs/code-analysis-2026-10-31.md)
