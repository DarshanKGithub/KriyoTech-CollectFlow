# MUI and live workspace data

## Installed packages

Installed from npm's `latest` release tags on 20 October 2026:

- `@mui/material`: 9.5.0
- `@mui/x-charts`: 9.15.0
- `@mui/x-data-grid`: 9.15.0
- Material UI Next.js integration and Emotion styling dependencies.

`Frontend/src/components/mui-provider.tsx` defines the shared product theme. The root layout includes the official Next.js App Router cache provider. Existing Overview charts continue to use live summary data. The payment register uses the Community Data Grid with search, filtering, sorting and pagination over the records returned by the API.

## Refresh behavior

`Frontend/src/components/live-data.tsx` provides near-live polling, not WebSocket or server-sent updates.

| Screen | Normal interval |
| --- | --- |
| Invoices and extraction status | 5 seconds |
| ERP sync runs and records | 10 seconds |
| Overview, approvals, exceptions, payments | 15 seconds |
| Fleet, dispatch, driver settlements, customer collections | 20 seconds |
| Notifications, email intake logs, vendor follow-ups, financial notes | 20 seconds |
| Needs attention | 30 seconds |

Sidebar counts refresh alongside access information every 60 seconds and on window focus.

The active screen refreshes through existing authenticated, workspace-scoped APIs. No background refresh initiates a payment, sends a message, or writes a business record. Existing API permissions remain in force.

The shared component prevents overlapping automatic requests, pauses when the tab is hidden/offline or a form has focus, and respects page-specific editing/submission pauses. It refreshes on returning to the tab or reconnecting. Failed automatic requests keep existing records on screen, display a warning, and back off to a maximum 120-second interval. Users can pause, resume or request a refresh.

Table filters and grid pagination stay in place while rows refresh. Background reads do not reset the invoice review form, ERP review dialog, payment form or driver settlement editor. Live data updates only the API's returned result set; this change does not expand backend pagination limits or introduce production push infrastructure.

## Validation

TypeScript compilation (`npx tsc --noEmit`) passed. No automated tests were added or run for this UI change.
