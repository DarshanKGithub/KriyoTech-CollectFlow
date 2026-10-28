# KriyoPay MUI migration

## Coverage

The shared MUI foundation is applied across navigation, Overview, invoices, approvals, exceptions, payments, reconciliation, fleet operations, driver settlements, procurement, integrations, reports, settings, billing, Super Admin, login and onboarding.

- One branded theme with consistent typography, spacing, controls and loading states.
- Responsive workspace and admin drawers, collapsible navigation, tooltips and mobile navigation.
- MUI cards, tables, status chips, alerts, accordions, forms and dialogs through shared `product-ui.tsx` components.
- Data Grids for invoices, payments, operational records and admin records; existing server pagination remains where applicable.
- Invoice upload dialog with file validation, drag and drop, progress feedback and automatic extraction messaging.
- Invoice review drawer and workflow stepper; trip and invitation progress components.
- Invoice Autocomplete and DatePicker in the payment form, with date controls on supplier and fleet report screens.
- ERP connection and sync tabs that preserve unsaved form state.
- Queued confirmation and input dialogs replace browser prompts; notices use Snackbars.
- Dashboard skeletons and existing live MUI charts.

### Loading skeletons

Reusable `ContentSkeleton` and `PageSkeleton` components provide table, card, form and chart placeholders. Loading indicators now cover invoice and approval queues, exceptions, exports, users, vendors, attention items, WhatsApp lists, settings, billing, operational records, payments, fleet operations, driver settlements, ERP connections and Super Admin screens. Shared Phase2 pages also show skeletons while their initial data loads.

Next.js route loading boundaries cover workspace, fleet and admin navigation. Skeletons have accessible status labels and respect reduced-motion preferences. Existing live refreshes retain loaded data; initial loading flags settle on completion or failure so errors remain visible. Submission and upload progress indicators remain action-specific.

## Compatibility decisions

Full-width layouts, existing branding, access-based navigation and existing backend workflows are preserved. Kanban boards have not been reintroduced. Tailwind utilities remain for layout and existing visual details; MUI owns the migrated interactive controls.

Shared control adapters preserve form names, values, refs and submit behavior. NativeSelect is used where native form submission is needed. Some date, month and datetime fields remain MUI TextFields using native input semantics; controlled date fields use MUI X DatePicker.

Existing export actions remain available. Default client CSV/print toolbar actions are disabled on migrated grids to retain the existing controlled export workflows. The implementation uses Community components.

Added dependencies: `@mui/x-date-pickers` 9.15.0 and `dayjs` 1.11.23.

## Validation

TypeScript compilation (`npx tsc --noEmit`) passed during migration and after the invoice upload dialog was added. Browser previews covered sign-in, Overview, the invoice grid and review drawer, mobile navigation and the payment form. Automated tests and complete financial transaction workflows were not run for this UI migration.

During browser preview, extraction was accidentally triggered again for the existing sample invoice `DEMO-VIDEO-20261019`. It completed and the invoice is now flagged for review. No approval or payment was submitted; its audit history was preserved.
