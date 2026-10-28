# Admin API (MVP)

## Transport fleet API (initial implementation)

All fleet routes require an authenticated tenant membership and the active workspace header (`X-Workspace`). Records are tenant-scoped. Fleet write routes are available to OWNER, FINANCE, PURCHASE (staff trip entry), and APPROVER for review actions as applicable; trip submitters cannot approve their own trip. Driver salary/settlement endpoints are not implemented in this first slice.

- `GET /api/v1/fleet/dashboard`
- `POST /api/v1/fleet/documents` multipart upload for private receipt evidence (PDF/JPEG/PNG/HEIC, up to 25 MB)
- `GET/POST /api/v1/fleet/vehicles`; `PATCH /api/v1/fleet/vehicles/{uuid}`
- `GET/POST /api/v1/fleet/drivers`; `PATCH /api/v1/fleet/drivers/{uuid}`
- `GET/POST /api/v1/fleet/trips`; `GET/PATCH /api/v1/fleet/trips/{uuid}`
- `POST /api/v1/fleet/trips/{uuid}/start` for a draft trip
- `POST /api/v1/fleet/trips/{uuid}/revenue` and `/expenses` to add lines while the trip is editable
- `DELETE /api/v1/fleet/trips/{uuid}/revenue|expenses/{line_uuid}` while the trip is editable
- `POST /api/v1/fleet/trips/{uuid}/submit`, `/approve`, or `/reject` (rejection requires a note)
- `GET/POST /api/v1/fleet/follow-ups`; `PATCH /api/v1/fleet/follow-ups/{uuid}` with action `start`, `resolve`, or `waive`

Approval and rejection actions use explicit endpoints. Approved trip margin counts only approved, actual revenue and expense lines. Missing receipts and expenses above their entered budget create follow-up items on trip submission. Receipt upload is available to fleet editors and documents remain tenant-scoped.

All routes are under `/api/v1/admin/` and require an authenticated active internal staff identity.

- `GET dashboard/summary`, `GET companies`, `POST companies`, `GET companies/{uuid}`
- `GET/POST plans`, `PATCH plans/{uuid}`
- `PATCH plans/{uuid}/features`, `GET features`
- `GET features`, `GET subscriptions`, `GET usage`, `GET audit-logs`
- `GET companies/{uuid}/entitlements`, `PATCH companies/{uuid}/entitlements`
- `POST companies/{uuid}/lifecycle` with an allow-listed status transition and required reason.
- `GET payments`, `GET billing-invoices`
- `POST auth/login`, `GET auth/me`

Tenant billing routes:

- `GET /api/v1/billing/summary`
- `POST /api/v1/billing/razorpay/create-order`
- `POST /api/v1/billing/razorpay/verify-payment`
- `POST /api/v1/billing/razorpay/webhook` (Razorpay HMAC signature required)

Document-backed invoices are queued for extraction automatically after supported intake when `EXTRACTION_PROVIDER` is configured to a non-manual provider. `POST /api/v1/invoices/{uuid}/extract/` remains available to retry manually after a failure. Extraction needs the configured provider, Redis, and a running Celery worker; results return to human review and never approve or pay an invoice automatically.

Responses never contain gateway secrets. The Razorpay key ID is returned only to authenticated tenant checkout; API and webhook secrets remain server-only. The webhook event list omits raw payment/customer payloads.
