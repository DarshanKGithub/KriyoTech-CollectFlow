# Super Admin solution access and feature catalog

The six solution groups confirmed by the product owner are InvoiceFlow, Procure, Reconcile, SettleView, Transport and DriverFinance. Pricing is INR per company per month. Launch prices were revised on 6 November 2026 after checking official public pricing pages; they are our commercial recommendations, not customer-approved contracts. See [market review](pricing-market-review-2026-11-06.md).

Open **Super Admin → Plans & features** to configure plan defaults and edit catalog prices. The company details page groups effective feature access by solution and shows the source of each grant. Only Super Admin may change catalog prices; a reason and before/after audit record are required. Existing plan access roles continue to control entitlement changes.

## Selectable solution packages

| Package | Monthly ₹ / company | Quarterly ₹ total | Annual ₹ total |
| --- | ---: | ---: | ---: |
| Reconcile | 499 | 1,497 | 4,990 |
| SettleView | 499 | 1,497 | 4,990 |
| Transport | 2,499 | 7,497 | 24,990 |
| DriverFinance | 799 | 2,397 | 7,990 |

These are real selectable Plan records, distinct from the feature-list estimates below. Existing plan checkout charges the selected package amount. A package price is not added again to its individual feature prices. Each package starts with five users, no invoice upload/AI extraction entitlement, and an explicit feature matrix. The current subscription model selects one plan; a combined solution offer must be configured as a separate plan rather than stacking subscriptions.

Reconcile enables payment tracking/bank reconciliation. SettleView enables settlement review plus shared payment access required by that workflow. Transport includes Transport operations and disables DriverFinance modules. DriverFinance includes its three finance modules plus fleet master access; it uses shared fleet reference records and does not include dispatch/trip execution. Catalog seeding retains already edited package prices and grants. New package creation writes an audit event.

## Starting fleet catalog prices

| Feature | Monthly ₹ / company |
| --- | ---: |
| Fleet master access | 0 |
| Live tracking & playback | 499 |
| Geofences | 99 |
| Dispatch & route planning | 399 |
| Trips | 299 |
| Vehicle & driver directory | 0 |
| Fuel | 299 |
| Maintenance & reliability | 199 |
| Vehicle & transport documents | 99 |
| Customers & transport orders | 199 |
| Return loads & bookings | 199 |
| Dock scheduling & detention | 99 |
| Alerts & exceptions | 0 |
| Customer shipment portal | 99 |
| Customer notifications | 99 |
| Reports & profitability | 199 |
| Driver workspace | 0 |
| Driver salaries, advances & settlements | 399 |
| Customer invoices & collections | 299 |
| Freight expense reconciliation | 199 |
| SettleView report review | 499 |

InvoiceFlow's individual features range from ₹0 to ₹499 per month. Procure matching, Reconcile payment tracking and SettleView report review are ₹499 each. These are individual-feature list prices. An enabled-feature sum is displayed as a catalog estimate and does not represent a discounted bundle, tax calculation or issued invoice. Zero-cost features still require an explicit/inherited access grant; a zero catalog price does not bypass role or company checks.

## Access behavior

- Fleet master access remains the parent gate for Transport and DriverFinance. Each new fleet subfeature can be enabled/disabled independently through a plan default or company override.
- A missing subfeature setting inherits existing effective fleet access. Explicit new settings take precedence. This preserves companies with a historical company-level fleet grant while enabling gradual configuration.
- User role and company lifecycle checks still apply. Disabling a module removes its navigation and blocks its dedicated API operations. Fleet vehicle, driver, customer, order and trip list reads remain shared reference data for other enabled workflows; disabling one module does not make its underlying shared records private from all other modules.
- Tracking intake, shipment public links and notification workers also check their corresponding feature, alongside the fleet master gate.
- This catalog groups some existing shared features under one solution: PO/GRN matching belongs to Procure; payment tracking belongs to Reconcile; SettleView is additionally controlled by settlement_review. Finer procurement/payment capability separation is not introduced by this change.

## Billing boundary

Individual feature catalog prices and enabled access are separate from payment capture. Current checkout charges the selected Plan monthly/quarterly/annual price, including the four solution packages above, and uses its current activation flow. This change does not add feature amounts to historical subscriptions, pending gateway orders or issued invoices, and does not grant features merely because a price is configured.

To charge customers for selected features, a subsequent checkout change must persist selected features and their price snapshots, calculate one reviewable quote, collect that amount, and activate only those purchased entitlements after verified payment. Until that is implemented, Super Admin manages access and the catalog is a pricing/configuration tool. Customer-visible billing screens must not claim that feature charges have been collected.
