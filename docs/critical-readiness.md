# Critical readiness work

## Invoice extraction reliability — implemented 20 October 2026

- Provider timeouts, connection errors, HTTP 408/429 and temporary server failures retry after 30, 60 and 120 seconds (four attempts total).
- Database claims prevent duplicate task deliveries from running extraction concurrently.
- Released jobs cannot apply late results over newer work.
- Invoice field edits are rejected while extraction is running.
- A scheduled maintenance task releases jobs unchanged for 15 minutes into an actionable failed state. The user can then retry extraction.
- Super Admin → Security shows database, Redis, scheduled worker heartbeat and extraction counts.
- Migration: `invoices.0006_extraction_recovery`.

### Operations

Run both Celery worker and Celery beat. Restart both after deploying these changes. Run only one beat scheduler per environment.

If workers are offline, run the recovery command independently from the backend directory:

```powershell
.\.venv\Scripts\python.exe manage.py recover_extractions
```

The maintenance task runs every minute. Its heartbeat lasts three minutes; this confirms one scheduled task executed, not that every worker is healthy. The maintenance task itself needs a working broker and worker. `EXTRACTION_STALE_SECONDS` defaults to 900 and must exceed normal processing and retry duration.

This admin panel is authenticated and is not a standalone infrastructure liveness endpoint. Failed jobs remain in history, so failure counts are cumulative.

### Validation status

The local database migration was applied successfully. Automated tests and full live extraction verification have not been run for this change.

## Remaining critical stages

1. Enforce branch access consistently across reads, writes, exports and related-record references; complete tenant isolation verification.
2. Configure production deployment, persistent document storage, supervised services, monitoring and backups; demonstrate a restore.
3. Implement admin MFA enrollment, login enforcement and account recovery.

These remaining stages are not complete. Local development readiness does not establish production readiness.
