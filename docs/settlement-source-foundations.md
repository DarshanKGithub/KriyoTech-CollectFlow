# Settlement sources and reviewed imports — Step 2

Step 2 snapshot; subsequent server pagination and reviewed internal-payment groups are documented in [reconciliation-evidence-and-groups.md](reconciliation-evidence-and-groups.md).

Implemented: 26 October 2026. Scope approved: both platform billing and client merchant accounts, with separate access.

## What is available

- Workspace **Settlement sources** (`/settlements`): OWNER/FINANCE can create bank/gateway source identities, stage reports, review imports and verify previously unknown operational provenance. AUDITOR can read/download evidence. Branch-scoped users require workspace-wide finance access; this release does not expose workspace-wide financial sources to them.
- Platform **Super Admin → Settlement sources** (`/admin-console/settlements`): SUPER_ADMIN/BILLING_ADMIN only. These accounts belong to KriyoPay subscription collections. Platform staff do not gain client workspace access through this endpoint.
- Workspace access follows the existing `payment_tracking` entitlement, including bank reconciliation. Bank and gateway identities have explicit ownership, provider/reference and currency. Identity cannot be edited after creation; accounts can be disabled with an audit entry.
- Import-only release: no credentials are collected, no live gateway API runs, and platform subscription credentials are never used for a client merchant.

## Workflow

1. Add an account with its provider, masked bank reference or merchant ID, and actual source currency. Use distinct identities for bank and gateway accounts.
2. For gateway reports, select the gateway and download the header-only CSV template. Map the provider report into the documented template; arbitrary native-provider layouts are not automatically mapped.
3. Upload CSV or values-only XLSX. The original bytes, SHA-256, source row numbers and normalized rows are retained. Invalid batches have row errors and cannot be approved; no partial observations are posted.
4. Inspect rows, arithmetic, account and missing-component warnings. Approve/reject with a review note. Missing evidence warnings require explicit acknowledgment.
5. Approval creates immutable source observations, not a payment, plan activation, refund request or confirmed bank credit. Repeated files and identical provider IDs reuse existing facts; conflicting facts require a new explicit correction/reversal, never an overwrite.

Example (synthetic source values):

~~~csv
record_type,external_id,currency,gross,fees,fee_tax,refunds,adjustments,net
SETTLEMENT,setl_demo,INR,100,2,1,0,0,97
~~~

## Evidence and accounting semantics

- Supported currencies: INR, USD, EUR, GBP, AED, SGD, AUD, CAD. Sources are kept separate; there is no FX conversion or cross-currency matching.
- Money uses exact decimals, up to 18 digits with two decimal places. Blank components stay null/unknown. Explicit zero remains zero.
- When all components are present, `gross - fees - fee_tax - refunds + adjustments = net` must hold exactly. Incomplete components require review; the system does not invent expected net.
- REFUND rows use a positive `amount` and optional payment reference. They record report evidence only. REVERSAL rows require the original provider ID/type and an exact full amount in the same account/currency; the original observation remains intact. Partial reversals are not supported.
- `expected_date` and `settled_date` are source calendar dates, not invented timestamps or proof of bank confirmation. Detailed timing stays in the original file.
- CSV must be UTF-8. XLSX processes the active worksheet, rejects formulas/macros, and requires identifiers in text cells to avoid spreadsheet rounding. Limits: 10 MB input, 10,000 rows, 32 columns, 200 ZIP entries and 50 MB expanded workbook. Error/warning responses show the first 100 notices; the original file retains complete evidence.
- Account locking, unique file/provider constraints and approval-time conflict checks protect repeat/concurrent uploads and approvals. Application endpoints do not edit/delete observations. Database operators can still change rows through direct SQL; this is not a claim of a tamper-proof ledger.

## Existing operational records and bank reconciliation

Supplier payments, customer collections, driver salary payments and bank statements now have nullable account/currency provenance. Historical records are deliberately not assigned an assumed account or currency. New operational payment entry paths also remain unverified until source evidence is explicitly recorded through **Verify legacy sources**; this verification flow supports both historical and newly recorded payments.

- Add/select the bank account, choose the record type, enter the existing record UUID and describe evidence. The action is tenant-scoped and audited; verified provenance cannot be overwritten.
- Operational supplier/fleet payments currently support INR only. Settlement observations and bank statements can retain the other listed currencies. This is not a multi-currency payable ledger.
- Bank import UI requires an active workspace bank account. Older API clients can omit it, retaining an explicitly unknown source that cannot be matched.
- Bank transaction duplicate checks are scoped to account/currency. Bank imports reject excessive precision and values outside the supported monetary range instead of silently rounding or overflowing; list and candidate amounts are returned as decimal strings.
- Candidate generation, manual matching and final confirmation require the same active workspace bank account, currency, amount and direction. Unknown sources cannot silently match. Previously linked legacy rows must be explicitly unmatched before verifying unknown provenance; clearing a link does not change the payment itself.
- Payment details and statement review offer verification links. Bank statement review offers a protected original download for files retained after this release. Earlier statements may not have original files and return a clear unavailable response.
- Existing bank candidate/list limits remain (latest 500 rows, bounded candidate search). Pagination, persisted candidate evidence and group allocations belong to Step 3. No settlement-to-bank group matching is claimed here.

## API surfaces

Tenant prefix: `/api/v1/settlements/`. Platform prefix: `/api/v1/admin/settlements/`.

| Endpoint | Purpose |
| --- | --- |
| `accounts` GET/POST | List scoped accounts / create immutable identity |
| `accounts/<uuid>` PATCH | Enable or disable only |
| `imports` GET/POST | Paginated batches / stage file with `account_id` |
| `imports/<uuid>` GET/POST | Batch metadata / reviewed decision and note |
| `imports/<uuid>?rows=1` GET | Paginated normalized source rows |
| `imports/<uuid>/source` GET | Authorized original-byte download |
| `records` GET | Paginated approved observations with decimal strings |
| `template` GET | Header-only CSV |
| `provenance` POST | Tenant-only operational source verification |

Lists use 25 rows by default (maximum 100 per page); accounts list is bounded to 200. Foreign tenant/account IDs return 404. Platform APIs require billing administrator access independently of tenant membership. Bank originals use the existing tenant API: `/api/v1/bank-reconciliation?source_for=<statement_uuid>`.

## Storage and deployment

Source files use `FinancialSourceStorage`, outside the public media root by default (`private_<media-directory-name>` beside MEDIA_ROOT). It deliberately has no public URL. Both download APIs authorize the request before opening the file.

Provision persistent private storage, include it in encrypted backups/restore procedures, restrict filesystem access and never expose that directory through Nginx/static hosting. Operators can configure Django `FINANCIAL_SOURCE_ROOT` for another private filesystem path. This release uses local filesystem storage; remote private object storage and retention/deletion policy are deployment work.

The following migrations were applied successfully to the local application database. They are additive:

- `settlements.0001`–`0002`: account/import/row/observation schema, constraints and private storage.
- `payments.0003`–`0004`: supplier payment provenance.
- `fleet.0016`–`0017`: salary payment and customer collection provenance.
- `phase3.0011`–`0013`: bank statement provenance and private original files.

From backend, with its virtual environment:

~~~powershell
.\.venv\Scripts\python.exe manage.py migrate settlements --noinput
.\.venv\Scripts\python.exe manage.py migrate payments --noinput
.\.venv\Scripts\python.exe manage.py migrate fleet --noinput
.\.venv\Scripts\python.exe manage.py migrate phase3 --noinput
~~~

Deploy the matching frontend/backend together and reload the backend. Existing worker/beat restart requirements from Step 1 remain; this step adds no scheduled provider synchronization.

## Verification

- Complete isolated PostgreSQL suite: **209 passed**, no skips. External urllib HTTP was blocked; Celery used in-memory transport and files used temporary private/public roots. Concurrency coverage includes repeated file staging and approval, existing bank-link races and refund reservations.
- Frontend: **22 tests passed** across seven files. Scope-specific endpoints, auditor controls, unknown money display, initialization retry and legacy matching controls are covered.
- TypeScript and ESLint passed. Production build generated **64 pages**; final download-error placement was subsequently covered by type/lint and frontend tests.
- Django check passed and migration drift check reported no changes.
- Initial sandbox production build could not create a generated directory (EPERM); the build succeeded with the required permission. Initial new-test fixture emails collided and old bank fixtures lacked provenance; fixtures were corrected without weakening source isolation checks.
- No live gateway requests, real payments or refunds were initiated. Provider-native layout compatibility, real merchant onboarding and production performance remain unverified.
