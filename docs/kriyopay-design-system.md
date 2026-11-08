# KriyoPay design system

This is the working design-system contract for incremental UI redesign. Existing finance, fleet and admin screens share providers and form wrappers, so tokens should be migrated deliberately. A screen may use the local shadcn-style primitives (`Frontend/src/components/ui`) or the existing MUI-backed product components; do not build a second equivalent control without a concrete need.

## Visual direction

- Enterprise operations product: high information clarity, restrained decoration, readable tables and visible status/freshness.
- Brand palette (6 November 2026): **emerald green `#16734A`** for primary actions, links and identity, with **warm cream `#E8DCC4`** restricted to brand accents. At the user's request, product backgrounds retain the previous neutral canvas, white cards/forms, neutral table headers, and original dark surfaces. Amber attention and red error states remain distinct.
- Light and dark themes remain supported. Status must include text/icon/context, not color alone.
- Typography uses a compact sans-serif stack, tabular numerals for money/counts, and clear page-title/section-label/body/caption levels.
- Use 4px spacing increments; controls target 36–40px height; touch targets should be at least 40px on small screens. Cards use a subtle border and little or no shadow. Reserve larger radii for dialogs and prominent surfaces.

## Current implementation baseline

`Frontend/src/lib/brand-colors.ts` is the shared TypeScript palette for Tailwind and the MUI finance tokens. `Frontend/src/app/globals.css` holds matching CSS variables for shadcn-style primitives and legacy dark-mode utilities. `Frontend/src/components/mui-provider.tsx` applies the same palette to controls, tables, drawers, dialogs and charts. Tailwind's slate/gray and status color families use their original palettes; the forest utility uses the approved brand green. New screens must use shared semantic tokens for product surfaces.

| Role | Light theme | Dark theme |
| --- | --- | --- |
| Primary / primary label | `#16734A` / `#FFFFFF` | `#E8DCC4` / `#16734A` |
| Canvas | `#F5F7F5` | `#101A17` |
| Card / form surface | `#FFFFFF` | `#18251F` |
| Sidebar navigation | `#FFFFFF` | `#18251F` |
| Text / secondary text | `#1F3D2B` / `#64705F` | `#E7F1EB` / `#A4B8AD` |
| Border | `#DCE5E0` | `#33483D` |

Use white labels on the emerald primary buttons for readable contrast. Charts must retain distinct warnings/errors and use the active theme's primary color for the main series. QR codes retain a plain white background for scanning.

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
