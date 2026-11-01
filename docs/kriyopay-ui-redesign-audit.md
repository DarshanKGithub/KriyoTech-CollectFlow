# KriyoPay UI/UX redesign audit

Audit date: 2026-11-01

## Product and architecture

KriyoPay is a multi-tenant business operations product with finance/AP, payment approvals, procurement, fleet operations, customer/vendor portals, and a separate internal admin control plane. The frontend is Next.js 14 App Router + React 18 + TypeScript. The backend is Django/DRF with PostgreSQL and background tasks. Tenant API requests use bearer tokens and an active workspace header; frontend navigation filtering is a convenience and server authorization remains authoritative.

The root layout wraps most routes in `WorkspaceShell`, `FormNavigationGuard`, product dialogs, and MUI providers. The shell owns tenant/workspace discovery, user profile and access refresh, workspace switching, role/entitlement filtered navigation, mobile drawer, theme toggle, notifications and sign-out. Admin console, auth, invite and public portal routes have separate/hidden shell behavior. Existing designs combine Tailwind classes, MUI components, and local `product-ui` wrappers. Replacing the shell or wrappers wholesale risks changing form, validation, focus, and authorization behavior.

## Route inventory

There are 80 `page.tsx` routes. Dynamic and nested routes are included below.

- **Workspace/home:** `/`, `/attention`, `/notifications`
- **Invoices and controls:** `/invoices`, `/email-intake`, `/duplicates`, `/bulk-actions`, `/exceptions`, `/follow-ups`, `/sla-rules`, `/approvals`, `/approval-rules`, `/compliance`, `/audit`, `/ai-review`, `/custom-fields`
- **Payments and finance:** `/payments`, `/settlements`, `/bank-reconciliation`, `/financial-notes`, `/billing`, `/reports`, `/exports`, `/exports/settings`
- **Procurement and counterparties:** `/vendors`, `/vendor-aliases`, `/vendor-portal`, `/purchase-orders`, `/grns`
- **Fleet:** `/fleet`, `/fleet/[feature]`, `/fleet/booking-history`, `/fleet/customer-invoices`, `/fleet/customer-notifications`, `/fleet/customer-portal`, `/fleet/customers`, `/fleet/dispatch`, `/fleet/dock-schedule`, `/fleet/documents`, `/fleet/driver-salaries`, `/fleet/driver`, `/fleet/exception-center`, `/fleet/finance-settings`, `/fleet/freight-reconciliation`, `/fleet/geofences`, `/fleet/live-tracking`, `/fleet/maintenance`, `/fleet/operational-reports`, `/fleet/orders`, `/fleet/reliability`, `/fleet/return-loads`, `/fleet/revenue-leakage`, `/fleet/settings`, `/fleet/truck-documents`
- **Workspace configuration and people:** `/settings`, `/users`, `/branches`, `/integrations`, `/integrations/erp`, `/integrations/gmail/callback`, `/whatsapp`
- **Internal platform admin:** `/admin-login`, `/admin-mfa`, `/admin-console`, `/admin-console/audit-logs`, `/admin-console/companies`, `/admin-console/companies/[tenantId]`, `/admin-console/payments`, `/admin-console/plans`, `/admin-console/security`, `/admin-console/settlements`, `/admin-console/subscriptions`, `/admin-console/usage`
- **Authentication and public flows:** `/login`, `/signup`, `/forgot-password`, `/reset-password`, `/invite/accept`, `/portal/[token]`, `/portal/shipment/[token]`

## UI and dependency audit

- Present: Tailwind CSS 3, Lucide React, MUI 9 (including Charts, Data Grid and Date Pickers), Radix primitives, class-variance-authority, local shadcn-style primitives under `src/components/ui`, product UI wrappers, skeletons, empty states, status badges, pagination, notification center, dialogs, drawers and a theme toggle.
- Absent: Aceternity UI, Framer Motion, Recharts, TanStack Table, React Hook Form, and Zod. MUI Charts/Data Grid and native/form-wrapper validation already serve some overlapping needs. Avoiding needless parallel libraries reduces migration and bundle risk; add a library only when a defined screen needs a capability the existing stack cannot provide.
- The theme supports light and dark mode, but many legacy screens use hard-coded light utility classes and are corrected with global dark-mode overrides. The brand palette is forest/emerald and slate; the requested navy/indigo direction is a product-level change and should be rolled out using tokens and regression checks rather than ad hoc overrides.
- Accessibility foundations include semantic headings, explicit labels, ARIA states, focus styles, and validation feedback, but these patterns vary across older screens. All redesigned screens need keyboard and responsive review.

## Existing behavior to preserve

- Authentication, refresh-token handling, workspace switching, feature/role navigation filtering and backend enforcement.
- Invoice matching/approvals, supplier payment instruction approval, Razorpay-backed platform billing, reconciliation, exports, procurement, ERP adapters, and portal flows.
- Fleet records and workflows: vehicles, drivers, orders, dispatch/trips, delivery milestones/POD, reviewed trip income and expenses, salary/settlement, maintenance, documents, customer billing, notifications, return loads, exceptions and reports.
- Live tracking is sourced from `/fleet/live-locations`, refreshed every 15 seconds, with phone GPS status/freshness, server ETA, and trip history from `/fleet/trips/{id}/location-history`. Route playback splits visual paths across GPS gaps. Geofences and events are backed by `/fleet/geofences` and `/fleet/geofence-events`. Phone capture requires the driver trip page and location permission. No production feature should claim GPS coverage without a provider or fresh driver sample.
- Existing location-history tiles are configured through `NEXT_PUBLIC_MAP_TILE_URL_TEMPLATE` and attributed to their map provider; the default is OpenStreetMap. Google Maps routing is a server-side ETA option when configured. A Google Maps JavaScript key/provider integration is not currently present.

## UX findings and design direction

1. The default `/` dashboard focuses on invoice volume, payable aging and invoice workflow. Fleet operators need a dedicated operations landing page and should reach live tracking and dispatch without traversing the long general navigation.
2. `/fleet` combines setup forms, trip entry, follow-ups, salary workflows and reports in one very large page. This creates high scroll/cognitive cost and should be decomposed into focused screens over subsequent slices while preserving deep links and workflows.
3. `/fleet/live-tracking` shows real live positions, but its primary layout is a grid of trip cards; operators cannot scan a fleet-wide spatial view. A map plus synchronized live-vehicle list is the first high-value control-center slice.
4. The shell is functionally rich and permission-sensitive, and the long fleet submenu needs to preserve operator context. Keep role filtering while retaining expanded sections and offering a compact Fleet module switcher.
5. The fleet module has meaningful operational data, but many roadmap features (fuel ledger, FASTag feed, E-Way Bill, load marketplace, WhatsApp delivery, AI assistant) require backend/provider work and must be labeled unavailable until supported. No mock data should be shown as live.

## Implementation plan and first slice

1. **Audit and guardrails:** this document records route, dependency, product and preservation findings.
2. **Design system:** document semantic tokens, component patterns, responsive layout and accessibility; introduce token changes gradually because many legacy MUI/Tailwind screens share the shell.
3. **Application architecture:** reorganize shell navigation around Finance, Fleet operations, Insights and Administration, preserving permission checks and public/admin route boundaries.
4. **Implementation:** redesign the fleet live operations control center first, then the fleet overview/dispatch and finance modules, payments/transactions, customers, analytics and settings. Split the large `/fleet` screen only as each workflow gets a replacement destination.
5. **Quality gates:** run frontend typecheck, lint, tests and production build; verify route permissions, API-backed loading/error/empty states, keyboard navigation, light/dark and narrow-screen layouts. Backend/API schemas are out of scope for presentation-only changes unless an audited requirement proves otherwise.

### Completed redesign increments

- **2026-11-01:** Reworked `/fleet/live-tracking` into a map/list/detail control center using `/fleet/live-locations` and existing route-history APIs. Kept the 15-second refresh, freshness classification, ETA method disclosure, and route playback. Added live/stale/waiting summaries, searchable vehicles, accessible selectable map markers, and a no-GPS map state.
- **2026-11-01:** Added a role-aware Fleet Operations snapshot to `/`, backed by `/fleet/dashboard` and (only when authorized) `/fleet/live-locations`. Renamed the landing page to Business overview and updated the workspace shell descriptor. Navigation groups now open only for the current route by default; role and entitlement filtering is unchanged.
- **2026-11-01:** Fleet navigation groups now retain the operator's expanded/collapsed choices across route changes and reloads; mobile navigation stays available until explicitly dismissed. Added a responsive Fleet module switcher and consistent table, form, alert and surface styling across `/fleet/**` routes.
- **2026-11-01:** Refined return-load booking history, vehicle reliability, shipment tracking links, and customer notification delivery into searchable/summary-led workspaces with loading, empty, error, and action states. Existing API routes and safety checks are preserved.
- **2026-11-01:** Reworked the Fleet exception center with at-a-glance case indicators, search, clearer case ownership/deadlines, and a focused review action while keeping the existing assignment, resolution, history, and export flows. Frontend typecheck passed after the Fleet navigation and page updates.
- No packages or API contracts were added or changed. Frontend typecheck, lint, 27 tests, and an isolated production build passed. Lint still reports the existing `<img>` warning in `/admin-mfa`.

## Technical decision for this slice

The tracking redesign consumes the existing live-location API and retains its 15-second refresh and route-history flow. The map uses the already configured and attributed tile provider rather than claiming Google Maps integration that the repository does not have. It displays only coordinates returned by the API; missing or stale GPS is represented as such.
