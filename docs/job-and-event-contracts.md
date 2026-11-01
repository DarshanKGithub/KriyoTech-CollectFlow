# Background job and event contracts

Status: required conventions for new transport work and the standardization target for legacy jobs. The Razorpay order-paid worker now follows the provider-I/O and claim-fencing rules below; existing jobs are being audited incrementally.

## Durable event and queue contract

- Persist the business mutation and its outbox/event record in the same database transaction. An `on_commit` callback may wake a worker, but it is not the durable queue; a periodic recovery task must find unsent/expired work.
- Queue messages contain stable record IDs and a schema/version reference, not credentials or an unbounded copy of customer data.
- Event identity is immutable and unique in its source scope. Reuse of an idempotency key with the same request returns the original result; reuse with different meaning or payload is a conflict.
- Event envelopes carry `event_id`, tenant and branch when applicable, aggregate type/ID/version, event type, occurrence time, schema version, correlation ID, and bounded payload. Secret material, raw authentication headers, and unnecessary personal data are excluded.
- Database uniqueness and row locks enforce claims. A worker records a short lease plus a random claim token, releases the transaction before external work, then commits only if its token is still current. Late results from expired workers are discarded.
- Handlers are idempotent. Duplicate delivery returns the terminal or currently-processing state without repeating financial effects. State transitions are monotonic; stale events cannot downgrade a captured payment, approved record, delivered shipment, or newer revision.

## Provider I/O and retries

Never hold a database transaction or row lock while calling GPS, routing, OCR/AI, ERP, messaging, payment, toll, or customer systems. Claim work and snapshot the request inputs in a short transaction, call the provider outside it, then re-lock and verify the claim token, current revision, enabled connection, and workspace lifecycle before storing the result. A provider timeout after a non-idempotent request is an ambiguous outcome: keep a reservation or `UNKNOWN` state and reconcile by provider reference before retrying.

Classify errors as validation/permanent, transient/retryable, rate-limited, authentication/configuration, or ambiguous outcome. Retries are bounded and use backoff; persist attempt count, next-attempt time, and a sanitized error code/message. Never retry a financial or dispatch mutation indefinitely or infer success from HTTP 200 alone.

## Management command contract

Commands that process queues must have a bounded `--limit`, validate all options, be safe to rerun, avoid logging secrets or full document payloads, and print a concise count of claimed/completed/retried/failed records. Commands that can replay or mutate external state must provide a dry-run or require an explicit confirmation flag. Scheduled beat tasks and commands call the same service function so retry and lifecycle rules do not diverge.

## Current adoption

Razorpay event processing uses a database claim token and five-minute lease, performs the `order.paid` verification GET after the claim transaction closes, and discards work whose token is no longer current. Outbound tenant webhooks use an atomic delivery claim and bounded retry; the `deliver_webhooks` command supports a bounded dry run. Gmail messages use a unique tenant/provider/message key and a 15-minute claim lease, skip active claims, recover expired claims, and fence attachment writes and completion by token. Scheduled Gmail polling re-searches its bounded recent window, so messages remain recoverable without a broker-only cursor. Customer shipment notices are persisted under a unique delivery key, claimed before provider I/O, and scanned again by the scheduled recovery task. Extraction and ERP workers already fence stale results and recover abandoned jobs. Remaining on-commit dispatches must keep a database recovery path; new transport modules must use this standard from their first migration.
