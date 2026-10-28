# Operations Guide

## Deployment

For local development, run Next.js and Django directly on the host and connect them to PostgreSQL 18 and Redis services. Container workflows are deferred. Production can run Next.js and Django behind HTTPS with managed PostgreSQL 18+, Redis, and private S3-compatible storage. Inject secrets at runtime. Run migrations as a controlled release step and health-check the API, database, Redis, and Celery worker.

Invoice extraction is queued automatically when a document-backed invoice arrives if `EXTRACTION_PROVIDER` is configured to a provider such as `gemini`. Run a Celery worker continuously alongside Redis (`python -m celery -A config worker -P solo -l info` from `backend`). If no worker is consuming the queue, new invoices may remain in `EXTRACTING`; monitor worker availability and queue depth. Extraction results always require human review.

## Backups and recovery

Back up PostgreSQL with point-in-time recovery where available and replicate document storage. Encrypt backups, restrict access, define retention with tenants, and test restoration. Reconcile document records against object storage during recovery.

## Monitoring

Track API errors/latency, database connections, Redis availability, Celery queue depth and oldest-job age, extraction duration/failure, upload/storage errors, email delivery outcomes, and counts by invoice/exception state. Alert on sustained queue age, failed migrations, storage/database failures, and repeated task failures.

## Jobs and incidents

Jobs should be idempotent and retry transient failures with bounded backoff. Permanent input/provider errors remain visible; exhausted jobs are retained for operator review and replay. Responders identify impacted tenant/workflow, preserve logs and audit records, avoid unsafe replay, recover service, and notify customers under contract. Never bypass approval or exception controls to clear a queue.

## Data and support

Support access is time-bound and audited. Export logs should contain job and tenant IDs without document contents. Remove tenant data only through an approved retention workflow that preserves records required by contract or law.
# Webhook delivery operations

The app writes webhook events to a tenant-scoped delivery outbox. To send due deliveries and process retries, schedule `python manage.py deliver_webhooks --limit 100` every minute using the host scheduler or a managed worker. The command is safe to run repeatedly; receivers should deduplicate on event ID because retries are at-least-once. After six failed attempts a delivery is marked `FAILED`; inspect delivery records in the API and correct/reactivate the endpoint before operational replay tooling is added.

The month-end checklist at `/compliance` records finance reviews and audit notes by tenant and accounting period. It is an operational worklist; it does not file returns, validate government registrations, or certify tax compliance.

Keep `WEBHOOK_FERNET_KEY` backed up outside the database. A random key has been generated in the local ignored `.env` for this development workspace. Do not commit it or use that development key in production.
