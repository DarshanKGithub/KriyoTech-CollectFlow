# Super Admin interface refresh

## Scope

The administration portal uses shadcn/ui (New York style) and Radix primitives, with KriyoPay forest green branding. MUI X remains responsible for charts and searchable, filterable, paginated operational grids.

- Collapsible desktop sidebar with remembered state; mobile navigation sheet.
- Breadcrumbs, account menu and authorized-page search (Ctrl/Cmd K).
- Overview: four summary cards, subscription status chart, attention queue, company portfolio and configuration readiness.
- Shared shadcn buttons, inputs, labels, status badges, tables and payment dialog across existing admin pages.
- Subscriptions, usage, audit and embedded billing tables: search across loaded records, column controls, pagination, refresh, persistent load errors with retry, loading skeletons and record details sheets.
- Plans and company feature access: accessible switches disabled during saving.

Financial metrics use the existing summary API. No synthetic trends or example financial figures are shown. Searches across loaded grid data are explicitly labelled; server-side company search is preserved. Backend authorization, audit records, payment approval and refund workflows remain authoritative.

## Component source

Components in `Frontend/src/components/ui` were sourced from the official legacy New York shadcn registry for React 18 / Tailwind 3 compatibility:

- https://ui.shadcn.com/r/styles/new-york/button.json (and equivalent component endpoints)
- https://ui.shadcn.com/docs/tailwind-v4
- https://github.com/shadcn-ui/ui/blob/main/LICENSE.md

Use the existing semantic tokens in Tailwind and globals.css for future components. Keep admin-specific presentation in components/admin and admin-console/admin.css.

## Checks

- TypeScript check passed.
- Next.js ESLint check passed without warnings.
- Production build passed, all 64 routes generated, using separate `.next-admin-preview` output.
- Signed-in browser review covered overview, plans, subscriptions and mobile navigation.
- No automated tests or financial write operations were run for this UI change.
