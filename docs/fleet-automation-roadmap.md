# KriyoPay freight automation

For the current eight-area implementation, activation dependencies, verification scope and rollout steps, see [fleet-client-rollout.md](fleet-client-rollout.md). The details below describe the original foundations.

## Implemented workflows

### Freight-file reconciliation

- Page: `/fleet/freight-reconciliation`
- API: `POST/GET /api/v1/fleet/freight-imports`; `POST /api/v1/fleet/freight-import-rows/{id}/reconcile|ignore`
- Imports CSV and XLSX/XLSM trip/freight ledgers (up to 20 MB and 10,000 rows), stages data, matches exact trip number/customer reference within the workspace, and flags missing/invalid references, amounts, types, or dates.
- A file checksum prevents processing the same file twice. Each row is reconciled once. A confirmed row creates a **draft** trip revenue or expense line; it never bypasses trip approval or initiates payment. Unmatched rows can be linked to a trip by a reviewer.
- Accepted headers include trip number/reference, type, amount, description, category, date, and fuel litres. Expense type values include `EXPENSE`, `COST`, `FUEL`, and `TOLL`; revenue type values include `REVENUE`, `FREIGHT`, and `INCOME`.

### Return-load suggestions

- Page: `/fleet/return-loads`; API: `GET /api/v1/fleet/return-loads`
- Scores open loads using normalized location text, including high-confidence spelling similarities, current truck/driver availability, pickup gap, configured capacity, and historical median journey time where a lane has at least three completed trips.
- It displays an estimated arrival only when there is sufficient lane history. Offers and confirmed bookings are now supported, with explicit customer acceptance and suitability review. Fuzzy location matches require explicit review.
- Vehicle type and kg/tonne capacity conversion are supported. Google Routes traffic lookup is implemented but needs account activation. Driver hours and legal truck-route restrictions still require explicit operator verification.

### Delivery-delay estimates

- API: `GET /api/v1/fleet/alerts`
- For an in-progress trip with a scheduled delivery and at least three completed trips on the same normalized lane, KriyoPay compares a historical median travel-time estimate against the due time and emits `PREDICTED_DELIVERY_DELAY` when late arrival is likely. Existing `DELIVERY_DELAY` alerts still report actual overdue deliveries.
- This is a historical baseline, not live GPS/traffic prediction. It does not assume an ETA when sample data is insufficient.

### Phone GPS for active trips

- Driver Phone View requests the driver's browser location while an assigned trip is `IN_PROGRESS`, then sends a phone GPS update every 30 seconds. The location endpoint only accepts updates from the assigned driver and only while that trip is active.
- Fleet → **Live truck tracking** refreshes every 15 seconds and shows the latest coordinate, accuracy, speed, freshness, and a map link. The backend stores only one latest GPS fix per trip; it does not keep a location trail.
- The driver must grant browser location permission, have network access, and keep the Driver Phone View open. A browser page cannot guarantee tracking after it is closed or suspended. Production access must use HTTPS; background tracking after the browser is closed requires a native app or installed tracker.
- Coordinates are tenant-scoped and the live view is limited to Owner, Finance, Fleet, and Approver roles. Expiring, revocable customer shipment links are available through the customer shipment portal; they do not expose driver phone GPS.

### Logistics-document workflow

- Page: `/fleet/documents`
- Upload API: `POST /api/v1/fleet/documents` with `logistics_kind=EWAY_BILL|CONSIGNMENT_NOTE|PROOF_OF_DELIVERY`; list/review API: `GET /api/v1/fleet/logistics-documents` and `POST /api/v1/fleet/logistics-documents/{id}/review`
- Documents are tenant-scoped and checksum-recorded. When AI extraction is enabled and the configured provider supports Gemini, it extracts candidate e-way bill, consignment-note, or POD fields and confidence estimates. Results remain **Needs review**. Expired-looking e-way bill dates and low-confidence fields get warnings.
- When extraction is disabled or the provider is `manual`, documents enter manual review with a clear status. The reviewer edits the JSON fields, links a trip/order, and confirms. Confirming a POD links its source file to the trip and may set the recipient name; it does not complete or approve the trip.
- OCR output is not proof of legal validity, a signature verification, or a compliance decision. Users must compare it with the source document.

### Fuel and route anomaly signals

- API: `GET /api/v1/fleet/alerts`; thresholds: `/api/v1/fleet/reminder-settings` (GET/PATCH); UI: `/fleet/settings`
- Adds review alerts for fuel price per litre and fuel spend per kilometre over configured limits, and odometer distance more than a configured multiple of the historical lane median when at least three trips have lane odometer samples.
- Existing alerts continue to check fuel efficiency against each truck's expected km/L, missing fuel quantities, duplicate receipt content, expenses over budget, low trip margin, late deliveries, and missing POD.
- These are review signals and do not label a driver or claim as fraudulent. Default alert thresholds should be tuned to each fleet and region.

## Configuration / requirements

- Run backend migrations (`python manage.py migrate`) to add freight batch/row and logistics document records.
- Run Redis and the Celery worker for automatic logistics-document extraction. With `EXTRACTION_PROVIDER=gemini`, set `GEMINI_API_KEY` and the existing `GEMINI_MODEL`. Without those, the review flow remains usable manually.
- Configure alert thresholds under Fleet → Reminder settings.
- To add road-distance, truck-specific dimensions/weight limits, traffic ETAs, live GPS or route deviation, select and configure a mapping/telematics provider. Google Maps Routes is now supported. Its credentials are not configured in this workspace; external route calls remain inactive until credentials and explicit workspace enablement are present.

## Client acceptance walkthrough

1. Upload a CSV/XLSX containing a trip reference, `type`, amount, and description. Review matched and unmatched rows.
2. Match an unmatched row to a trip, reconcile it, and confirm a draft ledger line appears in the trip. Approve it through the standard trip-finance workflow.
3. Add open orders after completed trips, compare return-load suggestions, inspect pickup gap/capacity/history warnings, and dispatch only after the operator's review.
4. Upload a sample e-way bill, consignment note, and POD. With Gemini configured, inspect extracted field confidence; otherwise edit fields manually. Link and confirm; check that POD is attached without silently changing trip status.
5. Configure fuel thresholds, then inspect fleet alerts after trip expense and odometer data are recorded. The checks need representative data to produce lane estimates.

## Scope boundaries

The code provides internal import/review automation, phone GPS while the driver page is active, and historical data signals. External bank statement import, carrier portals, hardware tracker feeds, traffic routing, legally authoritative e-way-bill verification, handwriting/signature authenticity, and autonomous dispatch are separate integrations and are not active until a provider/account is selected and configured.
