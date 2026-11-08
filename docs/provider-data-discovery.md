# Provider and sample-data discovery

Status: in progress for the first pilot. Pilot mix selected: driver phone GPS plus vehicle GPS trackers. As of 5 November 2026, the operator confirmed that no tracker vendor/model has been selected yet. Provider names, samples, account owners, and live access are still to be recorded. Never paste credentials, full driver/customer PII, or unredacted financial account numbers into this document.

## Pilot profile

| Input | Current value | Owner / next action |
| --- | --- | --- |
| Pilot fleet size and branches | Not supplied | Pilot operator to confirm |
| Operating states and routes | Not supplied | Select representative origin/destination corridors |
| Driver phone platform and offline needs | Not supplied | Confirm Android/iOS mix, upload cadence, background limits |
| Tracker vendor, model, protocol, and ID format | Not selected yet | Select one device family for the pilot and obtain its authorized sample export/API guide |
| Fleet GPS event cadence and expected history | Not supplied | Confirm per-moving/idle cadence and retention requirement |
| Customer delivery/POD process | Not supplied | Identify actual LR/GR/POD variants and approval workflow |

## Sample pack requested

Supply a small, authorized, anonymized or synthetic pack for each source. Preserve column names, units, state transitions, nulls, and ordering; replace personal and commercial identifiers consistently so cross-file joins still work.

| Source | Minimum useful sample | Fields to retain |
| --- | --- | --- |
| Phone GPS | One trip with normal movement, a long stop, a GPS gap, and late/offline sync | Device/trip pseudonym, captured and received time with timezone, lat/lon, accuracy, speed, heading, battery/network if available, sequence/event ID |
| Tracker GPS | Same trip window from one representative device; include ignition if supported | Provider/device pseudonym, event ID, device time, server time, coordinates, accuracy, speed, ignition, odometer, fuel level, provider status/error |
| Trip/dispatch | One multi-stop job plus one return-load example | Pseudonymous order/customer, stop sequence, coordinates or test addresses, windows, load/vehicle constraints, expected route and handover points |
| Fuel | Several consecutive fills for one truck, including one correction/partial fill and any refund/reversal if available | Vehicle pseudonym, trip/reference, date/time, odometer, litres, unit price, total, station, receipt/reference, transaction type, full/partial flag, tank capacity if known |
| Toll/FASTag | A short statement with successful, reversed, and disputed transactions if present | Tag/vehicle pseudonym, plaza, passage time, amount, transaction/reference ID, debit/reversal state |
| Maintenance and vehicle documents | One scheduled service, repair/breakdown, and expiry reminder set | Vehicle pseudonym, odometer, service/repair kind, date, cost, next due measure, insurance/PUC/fitness/tyre dates |
| LR/GR/E-Way Bill/challan | At least one example per document type used in the pilot | Document type, number/date, vehicle, parties, route, goods/weight, validity/expiry, penalty/reason; redact GSTIN/contact details consistently |
| POD | One signed delivery, one photo-based delivery, and one failed/partial delivery | Order/stop pseudonym, delivered time, recipient role (not personal name), signature/photo presence, exception/reason, file type and size |

## Provider and account readiness register

| Integration | Current code/config evidence | Account owner | Access/sandbox status | Blocker / next step |
| --- | --- | --- | --- | --- |
| Phone GPS | Existing driver location endpoint and persisted history/playback | Product/mobile lead to assign | Implemented; handset background behavior needs pilot validation | Confirm supported app versions, permission copy, offline upload behavior |
| GPS tracker | Generic HMAC-signed device adapter with device-to-vehicle/trip mapping | Fleet operator to identify vendor contact | Provider certification not done | Obtain authorized payload spec, sample, signing method, delivery retry policy |
| Google Routes | Optional route/ETA adapter; `GOOGLE_MAPS_ROUTES_API_KEY` is supported | Cloud/Maps account owner to assign | Local `.env` key is not configured; live access not checked | Confirm billing-enabled project, Routes API access, quota, allowed regions, data terms |
| Gmail intake | Read-only OAuth connector | Workspace admin to confirm | Client file and redirect URI are present in local `.env`; account consent/reachability not verified | Recheck OAuth test/published state, scopes, test users, callback registration |
| WhatsApp | Customer notices use approved template delivery | Meta Business admin to assign | Required access token/template settings are absent from local `.env`; live access not checked | Confirm Business verification, phone number, approved template and webhook URL |
| FASTag/tolls | No direct issuer integration committed | Fleet finance to identify issuer/provider | Not assessed | Obtain statement/API sample and permitted access path |
| Fuel card | Demo workspace includes clearly marked synthetic card-feed rows for a duplicate, an unmatched vehicle transaction, and a reference-matched refund; no live provider connector | Pilot fleet finance to identify authorized provider | Demo only; no provider account or real transactions configured | Select the pilot provider, obtain authorized sample/API access, and validate mapping and reconciliation before enabling a live connector |
| E-Way Bill | No government/authorized-provider integration committed | Compliance owner to assign | Not assessed | Confirm authorized GSP/API route, credentials process, sandbox and legal entity setup |

The local configuration check inspected only whether variable names were set, not their values. It found Gmail OAuth file/redirect settings present, and no Google Routes or WhatsApp credentials. This establishes local configuration only; it does not establish valid provider accounts or production readiness.

## Discovery acceptance

- Receive the sample pack above, or record a named blocker and date for each unavailable source.
- Record a business owner and a technical/account owner for each external provider.
- Verify sandbox reachability and limits with test credentials in the approved secret store; do not add secrets to this repository.
- Replay the GPS, fuel, toll, transport document, and POD samples through import/validation fixtures, with expected outcomes recorded.
- Keep manual CSV/document intake available when a provider has no authorized integration.
