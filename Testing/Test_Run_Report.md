# Test run report

- **Run date:** 2026-10-18
- **Scope:** local automated tests for the current workspace changes; gateway network calls mocked.
- **Backend:** `83 passed` (`pytest -q`, SQLite test override).
- **Admin-console focused suite:** `27 passed` after adding payment lifecycle cases.
- **Frontend:** `1 passed` (`npm test -- --reporter=dot`).
- **Frontend types:** `tsc --noEmit` passed.
- **Django configuration:** `manage.py check` reported no issues; settings resolve to Gemini extraction with a non-empty key and `gemini-3.5-flash-lite` (secret value was not printed).
- **Gemini API:** not called against the live service. Provider request/response handling is covered with a mocked API response.
- **PostgreSQL 18:** not run. `psql` is not available on PATH in this environment; the backend suite used its SQLite override.
- **Live Razorpay:** not run. No browser Checkout transaction or public HTTPS webhook was exercised; test scenarios use a mocked Razorpay API.
- **Operational drills:** PostgreSQL backup/restore, staging/production separation, monitoring and Celery alerting have not been verified.

Coverage added in this run: mocked Razorpay order → captured verification → webhook replay; provider `authorized` response rejection; failed payment lifecycle; multi-file email intake with an unsupported attachment quarantined; Gemini extraction request/response contract and manual fallback.

The detailed cases and release blockers are in [Test_Cases.md](./Test_Cases.md). Local suite success is not production sign-off.
