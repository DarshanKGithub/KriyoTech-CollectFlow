# Changelog

Notable product changes are recorded here. Existing MVP capabilities are summarized in `Plan.md` and `PRD.md`.

## Unreleased — Transport fleet foundation

- Added the initial tenant-scoped fleet module foundation: truck and driver directories, trips, trip revenue/expense lines, receipt references, missing-receipt follow-ups, trip review transitions, dashboard summaries, and a Fleet & Trips workspace page.
- Driver salary policies, advances, driver ledger, settlement/pay runs, mobile driver access, scheduled reminders, and accounting exports remain future stages.

## Unreleased — Automatic invoice extraction

- Document-backed invoices now queue configured extraction automatically after upload and supported email, Gmail, WhatsApp, and vendor-portal intake. Extraction remains an asynchronous, human-reviewed step; manual extraction retry and field correction remain available.
- Queue failures and provider failures are recorded as extraction failures for review. Redis and a continuously running Celery worker are required to process queued jobs.

## Unreleased — Phase 2: Automation, flexibility, and control

### Implemented MVP baseline

- Multi-tenant authentication and role-scoped invoice, vendor, procurement, exception, approval, and export workflows.
- Manual-review extraction fallback, three-way matching, matching tolerances, immutable audit events, and Tally-ready CSV export.
- Host-based local development with PostgreSQL 18; Docker is not part of the current local setup.

### Phase 2 implemented in this increment

- Added a private per-tenant email intake token and multipart webhook for supported invoice attachments. Message IDs are idempotent; files are size/type checked; checksums, ingestion history, and audit entries are stored.
- Added vendor name/GSTIN/email-domain aliases, ordered matching signals, confidence/method capture, and exact/near invoice-number duplicate candidates with human decisions.
- Added tenant matching controls for rate, quantity, and tax tolerances, ordered vendor signals, partial goods receipt behavior, and recorded service acceptance evidence.
- Added ordered approval rules with current-step authorization, bounded delegation, decision/history records, submitter self-approval protection, and strict opt-in auto-approval constrained by allowed vendors/amount, completed matching, duplicate review, and zero blocking exceptions.
- Added exception deadlines, overdue/escalation actions, in-app notifications, read state, and per-user preferences.
- Added editable vendor follow-up drafts. Sending requires an explicit user action and the configured Django email backend.
- Added payment allocations against net payable, credit/debit note maker-checker decisions, duplicate review, and audit entries. KriyoPay records payments but does not initiate bank transfers.
- Added invoice custom-field definitions/values and required-field checks before approval, preview-token bulk exception actions, and aging/outstanding/exception/forecast/month-end reports with CSV export.
- Added operator screens for these controls and Phase 2 migrations. Backend workflow tests and frontend typecheck cover the implemented flows.

### Phase 2 still in progress

- The email endpoint is provider-neutral and token-authenticated; provider-specific Gmail/Graph/IMAP polling, signature verification per provider, attachment OCR, and retry scheduling require external credentials/infrastructure and remain unconfigured.
- SLA escalation currently runs when an owner/finance user triggers the overdue escalation action; there is no background scheduler configured.
- Bulk preview/commit currently supports exception assignment and resolution. Other bulk operations, stored report snapshots, dashboard notification badges, and richer reports remain future enhancements.
- Vendor follow-up delivery depends on the configured Django email backend; local development uses the console backend by default.

### Future/out of scope

- Direct bank payment initiation, direct Tally XML posting, WhatsApp sending, provider-specific polling integrations, and AI-driven approval remain out of scope.

## Unreleased — Phase 3 first slice: WhatsApp Business

- Added tenant-mapped WhatsApp Business numbers, Meta webhook verification and signature checks, idempotent incoming message history, invoice-attachment intake, and an invoice source-channel marker.
- Added consent-confirmed drafts for approval requests, due-date reminders, and clarifications. Finance users explicitly review and send through a configured approved Meta utility template; delivery callbacks update message status.
- Added a WhatsApp workspace screen, vendor phone capture, backend-only integration variables, schema migrations, and focused webhook/send-guard tests.
- One-time approval links, automated reminders, provider setup validation, and multi-attachment recovery remain on the Phase 3 roadmap. See `PHASE3_PLAN.md`.
