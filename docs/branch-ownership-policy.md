# Branch ownership and access policy

Status: foundation policy for the first Indian road-freight pilot. Branch-scoped operations remain blocked on endpoints until their selectors and direct-object access enforce this policy.

## Access rules

- A tenant is the security boundary. A branch never grants access to another tenant.
- A member without branch scope has tenant-wide access according to their role. Owners and finance operators can use a consolidated tenant view; read/write permissions still follow the role matrix.
- A branch-scoped member may access only active branches explicitly assigned through `BranchMembership`. Deactivated assignments and branches grant no access.
- Owners administer branches and assignments. Branch-scoped actors can read only their assigned branch directory entries. They cannot edit membership, branch state, or tenant-wide settings.
- An endpoint that cannot filter every collection, aggregate, direct-object lookup, download, export, and background action by branch must reject branch-scoped members. It must not silently fall back to tenant-wide visibility.
- Customer users are scoped by customer authorization and shipment links; a branch assignment alone does not grant a customer access to company finance or fleet data.

## Record ownership matrix

| Record family | Ownership rule | Visibility rule |
| --- | --- | --- |
| Trips, transport orders, stops, dispatch assignments, geofences, dock appointments, POD and shipment notices | One owning branch, captured when work is accepted or created | Owning branch; tenant-wide roles may consolidate |
| Vehicle, driver, customer and vendor master records | Tenant-wide master identity, independent from operational ownership | Branch use is granted by an explicit active visibility/assignment mapping; do not infer it from a transaction join |
| Trip expenses, fuel, toll, maintenance and driver settlements | Inherit the owning trip, vehicle or driver branch at the time of the event | Owning branch; finance consolidation is explicit |
| Invoice, PO, GRN, payment, collection, tax and export records | Inherit a single source operation branch; multi-branch settlement/export records carry explicit branch allocations | Branch users see records and allocated amounts for their branch; cross-branch totals require a consolidated role |
| Shared platform bank accounts, catalogs and provider configuration | Platform-owned; tenant-specific accounts are tenant-owned | Never made visible through a tenant branch assignment |

Until owning-branch fields and visibility mappings exist for a record family, the API treats it as workspace-wide and denies branch-scoped access. Do not guess historical ownership during backfills: assign only from a verified source or route the record to an explicit review queue.

## Cross-branch handover

A handover is an auditable workflow, not an ownership edit. It records the object, source and destination branches, requesting and accepting actors, reason, requested/accepted timestamps, and the object revision at request. The destination branch gains operational ownership only after an authorized acceptance. The original owner remains responsible until acceptance. Rejection or expiry leaves ownership unchanged. Completed trips and issued financial documents retain their historical owner; a handover does not rewrite their accounting history. Every transition is idempotent and emits an event with an event ID and aggregate revision.

## Consolidated access and reporting

Tenant-wide access is derived from an unscoped membership, not from membership in every branch. Consolidated reports include only records the actor is allowed to see and label branch attribution. Cross-branch allocations are counted once in tenant totals and shown by allocation in branch totals. Exports and direct downloads apply the same rule as list and detail APIs.

## Implemented guardrails and rollout

The current release includes tenant-scoped branch creation and assignment, owner-only administration, assigned-branch directory filtering, and fail-closed behavior on finance, reconciliation, invoice, and other endpoints that do not yet apply owning-branch selectors. Existing regressions verify branch assignment tenant isolation, assigned-directory filtering, and denial of unscoped invoice and finance access for branch-scoped memberships. New owning-branch columns, visibility mappings, handover APIs, and branch-level financial allocations belong to the subsequent BRN-01 through BRN-03 implementation and require audited backfills before access is enabled.
