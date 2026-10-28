# MUI pagination

## Controls

`Frontend/src/components/list-pagination.tsx` provides Material UI TablePagination with first/previous/next/last navigation, totals, and 10/25/50 rows per page.

The shared local-list hook retains the current page on refresh, clamps it when records disappear, resets to the first page when a filter key changes, and resets when page size changes. Pagination controls sit outside table bodies and horizontal table scroll containers where practical.

## Coverage

- Invoices: server-side pages, accurate API count, selectable page size, stable default ordering and stale-response protection.
- Tally export queue: server-side pages and explicit export of the current page's invoices.
- Approvals, exceptions, vendors, workspace users, duplicate reviews and bank reconciliation.
- Needs attention: category filtering happens before pagination.
- Purchase order, goods receipt and audit lists through OperationalPage.
- Shared record tables: email intake logs, policies and other Phase2Tool records. Notification, follow-up, note and bulk-action lists also paginate; bulk selection retains IDs across pages.
- Fleet: trip lists, follow-ups, salary lists, customers, transport orders, dispatch, customer invoices and invoice-ready orders.
- Driver finance: pay policies, trip earnings, settlements and advances, with independent controls. Totals continue to use the complete loaded arrays.
- Fleet operational reports: display pagination leaves server CSV export unchanged.
- Admin company/payment lists and the shared admin data table. Company search resets the page.
- ERP inbox/outbox and local-record picker use Material UI Pagination with the API's existing page counts.
- Payment register keeps the MUI X Data Grid pagination already installed.

Small summary tables, charts, settings, dropdown choices and individual invoice/trip line items retain their existing layout.

## API contract

Invoice endpoints accept `page` (one-based) and `page_size` (maximum 50, default 25). MUI TablePagination uses zero-based page indexes; frontend requests convert them. Responses retain DRF's `count`, `next`, `previous`, `results` structure. Workspace scoping and permissions remain unchanged.

Other array-returning endpoints use pagination over the records already returned by those APIs. Existing server caps on those endpoints remain in place; these controls do not imply all historical records are fetched. This change does not alter APIs consumed by other pages into a new response format.

## Validation

- TypeScript compilation passed (`npx tsc --noEmit`).
- Backend invoice view syntax compilation passed.
- No automated tests were added or run for this change.
