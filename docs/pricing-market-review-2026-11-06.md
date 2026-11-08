# India SME launch pricing review

Reviewed 6 November 2026. Rates are INR per company per month unless a source states a different unit. This is a launch recommendation based on published alternatives and the current product scope, not proof of willingness to pay or operating margin.

## Official-page evidence

| Product / official source | Observed price and terms | How it informs KriyoPay |
| --- | --- | --- |
| [Zoho Books India](https://www.zoho.com/in/books/pricing/) | Standard ₹899 monthly or ₹749/month paid annually, 3 users; Professional ₹1,799 or ₹1,499 annually, 5 users; Premium ₹3,599 or ₹2,999 annually, 10 users. Taxes extra. | Broad SME accounting is available below our former ₹7,500 entry price. KriyoPay should charge for its approvals/reconciliation/transport value without requiring a high entry commitment. Supplier-invoice limits and AI automation are not equivalent across products. |
| [Zoho Expense India](https://www.zoho.com/in/expense/pricing/) | Standard ₹99/user/month monthly or ₹79 annually; Premium ₹199 monthly or ₹149 annually; minimum 5 users. GST extra. | Expense workflows have affordable entry options. Per-user rates cannot be compared directly with our company fee without a user count. |
| [SuperProcure](https://www.superprocure.com/pricing/) | Starter ₹7,200 monthly or ₹5,400/month billed annually, 50 trips; Professional ₹27,000 monthly or ₹22,140/month billed annually, 250 trips. Extra-trip and implementation charges are listed separately. | Provides a more advanced TMS benchmark, not a feature-equivalent substitute. KriyoPay's current pilot-stage transport scope supports a materially lower launch price. |
| [Fleetio](https://www.fleetio.com/pricing) | Essential US$5/vehicle/month monthly or US$4 billed annually; Professional US$7 and Premium US$10 billed annually. Contract and fleet-size conditions apply. | Per-vehicle economics justify monitoring the cost of serving larger fleets under a company fee. No INR conversion was used. |
| [Simply Fleet](https://www.simplyfleet.app/pricing-plan) | Main cards show Essential US$3 and Advanced US$5 per vehicle/month; annual cards show US$30/US$50 per vehicle/year; minimum 5 vehicles. | Supports bundling basic fleet functions. The same page has inconsistent older FAQ rates and a September price-change banner; those conflicting values were excluded from numerical recommendations. |

Vyapar's fetched page showed USD rather than a verified India offer, so it was excluded from the INR comparison. No third-party directory estimates or competitor claims about other vendors were used as verified prices.

## Recommended and applied standard plans

| Plan | Monthly | Quarterly total | Annual total | Existing monthly invoice / user limits |
| --- | ---: | ---: | ---: | --- |
| Trial | ₹0 | ₹0 | ₹0 | 20 / 2; 14-day trial |
| Starter | ₹1,499 | ₹4,497 | ₹14,990 | 100 / 3 |
| Growth | ₹3,499 | ₹10,497 | ₹34,990 | 400 / 10 |
| Control | ₹5,999 | ₹17,997 | ₹59,990 | 1,200 / existing configured user policy |
| Enterprise | Custom | Custom | Custom | Reviewed capacity and support agreement |

Annual payment equals ten monthly payments: approximately 16.7% less than twelve monthly payments. Quarterly is three monthly payments with no invented discount. Feature access and usage limits retain their existing configuration; a lower price is not a promise that every module is included in every plan.

## Feature-price approach

Basic duplicate checks, Tally CSV export, fleet directories, alerts and the driver workspace have no additional catalog fee. Smaller options cost ₹49–₹199; Fuel and Trips ₹299 each; Dispatch and Driver Finance ₹399 each; Tracking ₹499. Complete Transport's individual list-price sum is ₹2,787; DriverFinance ₹897; Procure, Reconcile and SettleView ₹499 each. InvoiceFlow's full list is ₹2,935, including optional SSO, integrations and support. These sums are catalog estimates, not separately implemented solution bundles or automatic extra charges on top of a purchased plan.

GPS hardware/SIM subscriptions, authorized provider feeds, paid Maps requests, WhatsApp delivery and implementation services need an explicit cost/usage agreement before a live pilot. Current APIs do not automatically surcharge them or calculate tax from this review. Do not sell unrestricted fleet/AI volume on the strength of these prices: invoice limits remain enforced, while fleet capacity and provider budgets require pilot review. Monitor support hours, AI cost, storage and provider spend before committing to a long contract.

## Application and verification

Follow-up package prices requested by the product owner are now separate selectable plans: Reconcile ₹499, SettleView ₹499, Transport ₹2,499 and DriverFinance ₹799 per company/month. Quarterly equals three months and annual equals ten. These four package prices replace a feature-list sum when that package is selected; they are not an additional charge on top of the individual features. The existing single-plan checkout supports them. Arbitrary purchase of individual add-ons and combining multiple packages still require a separate quoted/custom plan flow.

`apply_launch_pricing` previews all known Feature prices and standard INR plan price changes. `--apply` saves them atomically with before/after audit evidence. Enterprise and custom-plan slugs retain their prices. New orders for standard plans use revised rates. Existing pending order amounts and issued invoice amounts retain their snapshots; historical payments, subscriptions and feature grants are untouched. Feature-based checkout remains unimplemented, as documented in [solution pricing](solution-feature-pricing.md).

New catalog seeding uses the reviewed defaults. Old migrations remain historical records; do not edit them to deploy future commercial changes. Automated tests cover preview, audit, replay safety, unchanged pending orders/invoices/grants/custom plans and existing checkout verification.
