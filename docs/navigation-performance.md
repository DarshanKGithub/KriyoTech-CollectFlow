# Navigation and API performance

## Changes

- Workspace sidebar keeps its access/profile state during route changes. It refreshes on window focus and once per minute instead of reloading on every click.
- Sidebar badges request a compact tenant-scoped summary. This skips recent invoice serialization and financial analytics.
- Simultaneous default GETs share one network request, with a separate response body for each caller. Requests are scoped to access token and workspace. No completed API response is cached; writes and requests with custom options remain independent.
- Navigation prefetches a route on hover or keyboard focus rather than prefetching the entire visible sidebar.
- Invoice lists fetch the latest extraction in one bounded prefetch query, rather than querying confidence and extraction status separately for each row. Write responses still read the latest extraction after the action.
- Summary counts reuse status aggregates; Overview omits recent invoices because it no longer displays them.

## Client preview on this computer

The default `start-dev.ps1` runs Next.js development mode. Pages can compile on their first visit in this mode. For a client demonstration, stop the existing app processes and start the precompiled frontend:

```powershell
.\stop-dev.ps1
.\start-dev.ps1 -FrontendMode Production
```

The startup command builds into `Frontend/.next-preview`, starts `next start`, and also starts the existing backend, Redis and Celery services. The build happens once per startup and can take a few minutes; rebuild after frontend source changes. This is a local preview, not an internet production deployment.

If port 3000 is already occupied, the script keeps the existing frontend and prints a message. It does not silently replace another running server.

## Checks and limits

Frontend lint, TypeScript compilation, Python syntax and Django configuration checks are used for these changes. No automated workflow tests were requested. No before/after latency benchmark has been recorded, so a specific navigation-time reduction is not claimed. Backend response time, network conditions and initial JavaScript loading can still affect navigation.
