# Overview analytics

The Overview uses the shared MUI theme and responsive MUI X charts.

| View | Data and interpretation |
| --- | --- |
| Daily invoice uploads | Line/area chart of invoice creation counts by local calendar day. Includes every day in the selected 7-, 30- or 90-day period, including zero-activity days. Comparison uses the preceding period of the same length. |
| Current invoice workflow | Horizontal bars group current invoice statuses into processing, review, blocked, matching/approval, payment ready, exported and rejected. This is a current snapshot. |
| Approved balances by due date | Current approved/payment-ready/exported invoices with positive remaining balances, grouped into not overdue, 1–7, 8–30, 31+ overdue days and missing due dates. Remaining balance is the recorded invoice total minus payment allocations; cancelled and fully paid invoices are excluded. |
| Open exception types | Donut chart of open/assigned exceptions, with counts, percentages and the most frequent issue. One invoice can have multiple exceptions. |

Charts include totals, units, tooltips, accessible data tables and meaningful empty states. Chart animations are disabled. Loading skeletons match the chart grid. Snapshot timestamps and upload-trend controls make the time scope explicit. Existing auto-refresh remains available.

## API and access

`GET /api/v1/dashboard/summary?analytics=1&days=30` adds analytics to the existing response. Accepted periods are 7, 30 and 90 days; other values use 30. Existing summary callers do not request the additional analytics queries. Status counts now use one grouped query.

All aggregates are tenant-scoped. Balance analytics require an owner, finance or auditor role and the payment-tracking entitlement. Workspace links respect feature/role navigation access. No schema migrations or dependencies are needed.

## Validation

TypeScript and Python syntax compilation passed. Read-only browser inspection confirmed the live workspace's upload trend, workflow and exception charts, plus the zero-outstanding-balance state. No financial records were changed. Automated tests and populated-balance scenario verification were not run.
