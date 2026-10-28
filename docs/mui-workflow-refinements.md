# MUI workflow refinements

## Implemented areas

1. **Validation:** Shared forms display native constraint errors beside MUI fields and focus the first invalid field. Invoice corrections, trip creation, salary forms and payments also map named API validation errors to fields. Salary form failures clear their busy state. Backend validation remains authoritative.
2. **Searchable selectors:** Entity selectors for vendors, suppliers, customers, drivers, trucks, transport orders and purchase orders use Autocomplete, retaining native FormData values and reset behavior. Typed text cannot silently retain a previously selected record. Payments retain their invoice Autocomplete.
3. **Feedback:** WorkflowFeedback keeps outcomes visible and provides a read-only data refresh action on errors. Confirmed successes use severity-aware Snackbars. Uploads, invoice actions, imports, exports and ERP operations report their accepted or completed outcomes. Refresh actions do not replay financial writes.
4. **Breadcrumbs:** Workspace and admin breadcrumbs identify parent pages and current location. Workspace links respect visible navigation access.
5. **Grids:** Invoice, payment and shared record grids remember column visibility, row spacing and supported sorting per workspace/page. Trip and salary settlement lists offer searchable tables alongside the existing workflow cards. Open workflow reveals the correct card page. Grid empty-search states can clear filters. Default client exports remain disabled.
6. **Progress:** Status chips and indeterminate LinearProgress cover extraction, upload, import, export, ERP and driver updates. No unmeasured percentage is displayed.
7. **Quick details:** Read-only drawers are available for vendors, trips, drivers, payments and shared grid records. Existing forms, filters and workflow cards stay mounted.
8. **Empty states:** Reusable empty, search and failure states provide explanations and appropriate actions in shared grids, operational records and major finance/fleet lists.
9. **Notifications:** The workspace header shows an unread badge and Popover with recent notifications, refresh/error states, record links and explicit mark-as-read actions. The existing recipient-scoped API supplies records; links respect feature access. The count covers the API's latest 200 notifications.
10. **Driver navigation:** Mobile BottomNavigation switches between Trips, Check-in, Receipts and Profile. Check-in and expense forms remain mounted while switching sections. Profile reads the signed-in user's existing account details. Existing offline submission behavior is retained.

## Invoice API support

Invoice search now matches invoice number, supplier, vendor and PO number within the existing tenant-scoped queryset. Search text is capped at 200 characters. Search/status filters and supported date/amount ordering run on the API across all pages. The invoice grid disables page-only quick filtering.

## Validation and limits

TypeScript compilation and Python syntax compilation are used for this change. Read-only browser previews covered Overview, invoice filters/grid and the searchable trip form. Full transaction workflows, a signed-in driver session and automated tests were not run. No dependencies or database migrations were added.

Existing API permissions, financial checks and idempotency protection continue to enforce business rules. Local grid preferences store presentation settings rather than financial records or search text.
