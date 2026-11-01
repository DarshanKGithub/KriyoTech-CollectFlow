# KriyoPay design system

This is the working design-system contract for incremental UI redesign. Existing finance, fleet and admin screens share providers and form wrappers, so tokens should be migrated deliberately. A screen may use the local shadcn-style primitives (`Frontend/src/components/ui`) or the existing MUI-backed product components; do not build a second equivalent control without a concrete need.

## Visual direction

- Enterprise operations product: high information clarity, restrained decoration, readable tables and visible status/freshness.
- Brand direction: deep navy for structural chrome, professional blue for primary actions, emerald for successful/healthy states, warm amber for attention, red for errors, slate neutrals for surfaces and dividers.
- Light and dark themes remain supported. Status must include text/icon/context, not color alone.
- Typography uses a compact sans-serif stack, tabular numerals for money/counts, and clear page-title/section-label/body/caption levels.
- Use 4px spacing increments; controls target 36–40px height; touch targets should be at least 40px on small screens. Cards use a subtle border and little or no shadow. Reserve larger radii for dialogs and prominent surfaces.

## Current implementation baseline

`Frontend/src/app/globals.css` defines the shared CSS variables consumed by Tailwind and shadcn-style primitives. `Frontend/src/components/mui-provider.tsx` defines MUI palette, typography, radii and control styles. `Frontend/tailwind.config.ts` maps semantic colors and radius to those variables. The existing forest/emerald palette and hard-coded legacy classes are still in use; a global brand-token swap is intentionally deferred until the component families are migrated and reviewed together.

The live operations screen and unified landing dashboard use the semantic patterns below as the first redesign slices:

| Purpose | Pattern |
| --- | --- |
| Page surface | Neutral canvas with compact title, one-line description and explicit refresh state |
| Cross-module landing | Business overview keeps finance reporting and adds role-aware operational KPIs with links to dispatch and live fleet |
| Navigation | Permission-filtered groups; preserve user-expanded groups across routes and reloads, and auto-open the current route's ancestors |
| Live status | Emerald + “Live”; amber + “Stale”; neutral + “Waiting for GPS” |
| Data validity | API coordinates only; missing GPS has an explicit empty state |
| Operations layout | Fleet-wide map and searchable vehicle list beside a selected-trip detail panel |
| Density | Four compact operational counters, a map, then list/detail; no decorative charts without a real series |
| Responsive | Stack map, list and trip details on narrow screens; use a two-column control-room layout on wide screens |
| Accessibility | Semantic headings, text labels, keyboard-operable markers, selected state, map attribution and visible focus |

## Component and library policy

- Tailwind + local `ui/*` primitives are the default for new presentational surfaces; Radix powers interactions where already available.
- Existing MUI Data Grid and Charts remain supported. Do not add TanStack Table or Recharts until a concrete limitation is documented.
- Forms should keep current API payloads and validation behavior. Adopt React Hook Form/Zod only for a new complex form where native/product form validation is insufficient.
- Use Lucide consistently. Do not add Framer Motion or Aceternity for effects that CSS transitions can handle; respect reduced-motion preferences.
- Maps must use an approved, configured, attributed provider and only show API-backed location data. Google Maps is not yet a frontend dependency; current live map reuses the existing tile-provider configuration.
