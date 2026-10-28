# Fleet operations rollout and activation

## Implemented application workflows

| Area | Workflow and pages |
| --- | --- |
| Predictive ETA | Google Maps Routes adapter calculates road distance and traffic ETA from an active trip's fresh phone GPS. Fleet settings explicitly enable provider calls. Celery Beat refreshes every five minutes. Historical estimates remain available when sufficient lane history exists. Continuous accurate phone updates can flag stops of at least 15 minutes within 200 m. Route monitoring flags fresh GPS more than 2 km from the previously computed road path, which is cached for 30 minutes. Confirmed delay/stop cases record the operator's reason on the trip. |
| Revenue leakage | `/fleet/revenue-leakage` compares delivered orders, approved actual trip revenue, approved detention additions, customer invoices, partial collections, and confirmed bank reconciliation. A suggested or merely matched transaction does not count as reconciled. Confirmed reconciliation groups are supported. Existing bank reconciliation remains the source for matching/confirming supplier payments, customer collections and driver payments. Cases and CSV exports are available in the exception center. |
| Detention | `/fleet/dock-schedule` records arrival, loading start, loading finish and departure separately. `/fleet/customers` supports customer-specific free time and hourly terms. Check-in snapshots the terms so later settings changes do not rewrite old estimates. Completed appointments can prepare one detention revenue draft on an editable trip. Normal trip review approves it, after which customer invoicing adds it to agreed freight. Pending detention drafts block invoicing. No charge is posted merely because a truck waits. |
| Return-load booking | `/fleet/return-loads` records proposed rates, negotiation notes, explicit customer acceptance and operator suitability confirmation. Configured vehicle type and capacity units are checked, including kg/tonne conversion. Existing `/fleet/dispatch` and return-load booking share truck/driver locks. Open breakdowns prevent assignment. `/fleet/booking-history` preserves offers and permits reasoned cancellation only before pickup and before financial records exist. Cancelled trips remain in history; orders reopen. |
| Fuel and expenses | `/fleet/exception-center` collects existing fuel, receipt, budget, route-distance and margin signals. A further comparison requires at least five earlier trips with the same truck and lane, approved actual fuel records, valid odometers, and cargo weights within 20%. It compares litres/km with that historical median. Missing context does not produce a guessed anomaly. Reviewers Confirm, Dismiss, Resolve or Reopen with a reason. Changed source evidence or policy reopens a previously closed case with an audit entry. |
| Maintenance | `/fleet/maintenance` records failure codes, breakdown and return-to-service times. `/fleet/reliability` merges overlapping downtime intervals, shows recurring failure counts and recorded maintenance cost per odometer kilometre, and explains assignment risks. Fleet staff can configure existing truck type and capacity units there. These are record-based warnings, not a statistical breakdown prediction. |
| Customer shipment portal | `/fleet/customer-portal` creates seven-day links and revokes them. Only a hash of each token is stored. The customer page shows shipment status, ETA and milestones; it downloads that shipment's POD and issued invoice as a printable HTML document. Issue/dispute submissions become tenant-scoped exception cases. A reviewer must provide a separate customer-facing response when resolving one; private review notes are not published. Driver identity, phone GPS and unrelated documents are not exposed. Revocation, expiry, deleted workspaces and disabled Fleet access invalidate the public view. |
| Exception automation | `/fleet/exception-center` supports owner assignment, deadlines, optimistic concurrency checks, decisions, review notes, audit history, status filters, server pagination and CSV export. New cases default to a fleet operator or workspace owner. Scheduled monitoring escalates overdue cases using configured roles, channels and escalation interval. Source evidence and policy fingerprints are retained. `/fleet/customer-notifications` shows customer delivery attempts and safely authorizes retries after provider checks. |

## Background services

Restart the backend, Celery worker and Celery Beat after deploying the migrations and code.

Tracking uses a separate Django cache alias, `fleet_tracking`, backed by the existing `REDIS_URL`. `FLEET_CACHE_URL` can override its location. Keys are namespaced separately from Celery. This shares short-lived stop and route geometry state between web and worker processes. GPS intake remains available when this optional monitoring cache is unavailable. Isolated SQLite tests use an in-memory tracking cache.

- `fleet.tasks.maintain_fleet_exceptions`: every five minutes.
- `fleet.tasks.refresh_fleet_routes`: every five minutes; only explicitly enabled workspaces with a server key are queried.
- `fleet.tasks.maintain_customer_notices`: every minute.
- Existing fleet reminders, ERP import/retry jobs and bank reconciliation jobs remain active according to their existing configuration.

Customer notice events are deduplicated across links by workspace, trip, recipient, channel and event. A provider timeout is recorded as **UNKNOWN** and requires a provider-log check before retry. Worker interruption after a send also becomes UNKNOWN. A rate limit gets bounded scheduled retries. Attempts and signed delivery callbacks are audited. Sends and route lookups run as individual bounded jobs rather than one long series of external requests inside a monitoring job. Customer notification opt-in and its source must be recorded when creating the shipment link; customers can stop updates from that page.

## External activation: accounts are not ready

The user selected Google Maps Routes and email plus WhatsApp Business, and confirmed that the Google/Meta accounts are not ready. The local SMTP server configuration is present. No live provider traffic or customer messages were sent during implementation tests.

Configure secrets in the server environment, never in frontend variables or source control:

```dotenv
GOOGLE_MAPS_ROUTES_API_KEY=
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_GRAPH_VERSION=
WHATSAPP_SHIPMENT_TEMPLATE=
WHATSAPP_TEMPLATE_LANGUAGE=en_US
WHATSAPP_APP_SECRET=
WHATSAPP_WEBHOOK_VERIFY_TOKEN=
```

Use an API version supported by the Meta account. The approved shipment template must have three body parameters in this order: **order number**, **shipment status**, **estimated arrival**.

Configure Meta's public HTTPS callback as:

`https://YOUR-BACKEND/api/v1/fleet/public/whatsapp-status`

GET verification checks the configured verification token. POST callbacks require an HMAC SHA-256 signature using the app secret. Supported delivery states are SENT, DELIVERED, READ and FAILED; delayed callbacks cannot regress a delivered/read message to an earlier state. The delivery queue distinguishes provider acceptance from recipient delivery.

Enable Google traffic ETA under Fleet → Reminder settings after account setup. API keys should be restricted to the server and Routes API. Destinations must be sufficiently specific addresses. Google DRIVE routes do not certify truck dimensions, hazardous-goods access or driver working-hour compliance: dispatch confirmation explicitly requires an operator to verify these restrictions.

## Verification and acceptance

Automated tests use an isolated SQLite test database and stub external providers. They cover tenant boundaries, stale review protection, revocable public access, detention rate snapshots and invoice totals, booking cancellation and duplicate assignment, notification deduplication and uncertain sends, Google response handling, open breakdowns, capacity conversion, signed callbacks and contextual fuel comparisons.

Production acceptance still requires real account activation and representative operating data:

1. Enable a demo workspace, configure vehicle type, capacity/unit, customer rates, and precise addresses.
2. Run a phone trip over HTTPS with GPS permission and the page open. Confirm Google ETA and road distance; check provider quota and the operator's truck-route review.
3. Check in at a dock, finish loading, depart, prepare detention, submit the trip and have another authorized reviewer approve it. Confirm the customer invoice includes approved detention exactly once.
4. Record an offer, confirm acceptance, verify the assigned trip in dispatch, and cancel an unstarted booking with a reason. Verify its history and reopened order.
5. Create a shipment link, check its limited view, report an issue, download POD/issued invoice, then revoke it and verify it no longer works.
6. With explicit customer consent and designated test recipients, verify real SMTP and WhatsApp template acceptance and signed delivery callbacks. Check unsubscribe and uncertain-result handling.
7. Import real or clearly labelled test bank transactions through the existing reconciliation center, match and confirm collections, and verify the revenue review updates.

Live external delivery, provider billing/access, mobile background operation after browser suspension, and PostgreSQL concurrency under production load have not been certified by the SQLite workflow tests.

## Provider references

- [Google Maps Routes: compute road routes and traffic-aware duration](https://developers.google.com/maps/documentation/routes/compute_route_directions)
- [Meta WhatsApp Cloud API](https://developers.facebook.com/docs/whatsapp/cloud-api/)
