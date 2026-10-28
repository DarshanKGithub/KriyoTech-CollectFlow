# KriyoPay product risk review — 20 October 2026

## Assessment

The product has confirmed runtime failures and access/financial-integrity defects that should be fixed before unrestricted client use. This review did not modify application behavior or customer records.

P1 means a release-blocking workflow, access or accounting defect. P2 means a significant operational or usability issue. No P0 finding is asserted in this review.

The most urgent fix order is: cross-company document isolation → fleet PostgreSQL crashes → fleet alerts → invoice/payment state controls → concurrent payment locking → branch enforcement → shared login protection.

## Confirmed defects

### 1. P1 — Another company's supplier/document can be attached to an invoice and the document read

**Evidence:** A temporary API test created an invoice in company A using a supplier and source-document ID from company B. Creation returned 201, the response exposed company B's supplier name, and company A's invoice source endpoint returned company B's document bytes with HTTP 200. Only synthetic test data was used. The attack requires an authenticated permitted user and knowledge of the foreign record IDs.

**Cause:** InvoiceSerializer exposes `vendor` and `document` as writable model relationships without scoping their querysets to the active tenant or checking their tenant on create/update. The invoice queryset itself is tenant-filtered, but the source endpoint trusts the invoice's linked document.

**Locations:**

- [InvoiceSerializer relationships/create](E:/Companies_Work/GearLogic_Automation/Projects/KriyoTech-CollectFlow/backend/invoices/serializers.py:9)
- [Source document endpoint](E:/Companies_Work/GearLogic_Automation/Projects/KriyoTech-CollectFlow/backend/invoices/views.py:226)

**Fix:** Scope related-record querysets to the request tenant, validate relationship ownership on both create and update, and independently fail closed when reading a document whose tenant differs from the invoice tenant. Add API tests for foreign suppliers/documents and nested relationships.

### 2. P1 — Trip actions and customer invoice creation can crash on PostgreSQL

**Evidence:** A read-only probe against the local PostgreSQL database used the same queryset as trip actions and a random nonexistent trip ID. PostgreSQL raised:

`NotSupportedError: FOR UPDATE cannot be applied to the nullable side of an outer join`

The probe requested no real customer row and made no changes.

**Cause:** `FleetTrip.transport_order` is nullable. The code uses `select_for_update()` together with `select_related("transport_order")` or `select_related("transport_order__customer")`, applying the lock to the nullable joined relation. This fails before the action can proceed, including for trips that actually have an order. SQLite ignores these row-lock semantics, so SQLite-only tests miss the defect.

**Locations:**

- [Trip action queryset](E:/Companies_Work/GearLogic_Automation/Projects/KriyoTech-CollectFlow/backend/fleet/views.py:696)
- [Transport invoice creation queryset](E:/Companies_Work/GearLogic_Automation/Projects/KriyoTech-CollectFlow/backend/fleet/views.py:254)
- [Nullable trip/order relationship](E:/Companies_Work/GearLogic_Automation/Projects/KriyoTech-CollectFlow/backend/fleet/models.py:126)

**Fix:** Lock the intended base row explicitly, for example `select_for_update(of=("self",))`, and lock related order rows separately where business concurrency requires it. Audit the remaining locking joins and run workflow tests on PostgreSQL.

### 3. P1 — Fleet alerts currently return HTTP 500

**Evidence:** The local Django log contains the exact failure for `/api/v1/fleet/alerts`. A fresh temporary-workspace API test reproduced HTTP 500 even with no trips.

`ValueError: chunk_size must be provided when using QuerySet.iterator() after prefetch_related()`

**Cause:** The alerts queryset prefetches expense/revenue lines, then calls `.iterator()` without a chunk size. The frontend ignores a non-OK alerts response and can continue to show an empty alert list, so missing alerts may appear to mean there are no problems.

**Locations:**

- [Fleet alerts iteration](E:/Companies_Work/GearLogic_Automation/Projects/KriyoTech-CollectFlow/backend/fleet/views.py:450)
- [Fleet page response handling](E:/Companies_Work/GearLogic_Automation/Projects/KriyoTech-CollectFlow/Frontend/src/app/fleet/page.tsx:51)

**Fix:** Use supported chunked iteration or iterate the prefetched queryset directly; show an explicit alerts-load error; audit other prefetch/iterator combinations. Test both empty and populated workspaces.

### 4. P1 — Invoice payment recording bypasses approval readiness

**Evidence:** A temporary API test posted a payment of 100 against an invoice in REVIEW_REQUIRED. The payment endpoint returned 201, and the invoice became payment_status PAID while its workflow status remained REVIEW_REQUIRED.

**Cause:** PaymentRegister validates supplier ownership and outstanding amount, but does not require an approved/payment-ready invoice or reject active blocking exceptions before creating allocations.

**Location:** [Invoice payment creation](E:/Companies_Work/GearLogic_Automation/Projects/KriyoTech-CollectFlow/backend/invoices/phase2.py:143)

**Fix:** Require the allowed payment workflow states and resolved blocking exceptions under the same transaction/row locks used to validate balances. Return a state-conflict response when payment is not allowed. Apply the same rule to every payment entry path.

### 5. P1 — Paid/exported invoice amounts can be rewritten without a correction or reversal

**Evidence:** A temporary API test created an exported, paid invoice with total 100 and an allocation of 100. PATCHing invoice_total to 1 returned 200. The allocation remained 100, the payment flag remained PAID, and the invoice was moved back to REVIEW_REQUIRED.

**Cause:** InvoiceSerializer.update accepts writable invoice financial fields and always resets workflow status to REVIEW_REQUIRED. The view blocks editing while EXTRACTING, but does not freeze posted/paid/exported records. `payment_status` is also absent from the serializer's read-only field list.

**Locations:**

- [Invoice update behavior](E:/Companies_Work/GearLogic_Automation/Projects/KriyoTech-CollectFlow/backend/invoices/serializers.py:33)
- [View update guard](E:/Companies_Work/GearLogic_Automation/Projects/KriyoTech-CollectFlow/backend/invoices/views.py:260)

**Fix:** Define an explicit edit-state policy. Lock posted financial values; derive payment status from valid allocations; route corrections through auditable credit/debit notes or reversals. Record before/after versions where edits remain permitted.

## High risks established by code review

### 6. P1 — Concurrent payments can both pass the outstanding-balance check

PaymentRegister reads invoice/allocation balances, checks the requested amount, and then inserts payment/allocation rows. It does not acquire invoice row locks. Two requests with different idempotency keys can read the same outstanding balance before either commits, then both insert allocations. An atomic block alone does not serialize that check-and-write sequence. The idempotency lookup and insert also have a race: the database uniqueness constraint can reject a concurrent duplicate with an unhandled error.

**Location:** [Balance check and payment insert](E:/Companies_Work/GearLogic_Automation/Projects/KriyoTech-CollectFlow/backend/invoices/phase2.py:161)

**Fix:** Lock all allocated invoices in deterministic order, recalculate active balances while holding those locks, validate idempotency payload consistency and handle uniqueness conflicts as safe replay/conflict responses. Add a concurrent PostgreSQL test. This race was identified from the code; simultaneous payment requests were not executed in this audit.

### 7. P1 when branch restrictions are relied upon — Branch assignments do not isolate core financial records

Membership has `branch_scope_enabled` and BranchMembership assignments, but the core invoice queryset filters only by tenant. Invoice and procurement records inspected here have no branch ownership field. The new ERP API deliberately rejects branch-scoped users, but that does not implement branch isolation for the existing product.

**Locations:**

- [Branch membership metadata](E:/Companies_Work/GearLogic_Automation/Projects/KriyoTech-CollectFlow/backend/accounts/models.py:20)
- [Invoice tenant-only queryset](E:/Companies_Work/GearLogic_Automation/Projects/KriyoTech-CollectFlow/backend/invoices/views.py:205)
- [Invoice data model](E:/Companies_Work/GearLogic_Automation/Projects/KriyoTech-CollectFlow/backend/invoices/models.py:8)

**Fix:** Either present branches as organizational metadata until enforcement exists, or implement branch ownership and enforce assigned scopes consistently across reads, mutations, related IDs, documents, exports and background jobs. This is a code/data-model finding, not a reproduced cross-branch record test.

### 8. P1 before public exposure — The shared login path bypasses the dedicated admin login throttle

The dedicated admin login view has ScopedRateThrottle. The ordinary `/auth/login` view has no throttle class, authenticates internal staff through UnifiedLoginSerializer, and issues tokens that IsAdminStaff accepts. The frontend's login page uses this shared path. Default throttle rates are configured, but no default throttle classes are enabled. Thus the dedicated admin endpoint's limit does not protect every staff login path. Admin MFA is also absent.

**Locations:**

- [Shared login view](E:/Companies_Work/GearLogic_Automation/Projects/KriyoTech-CollectFlow/backend/config/urls.py:8)
- [Shared staff authentication](E:/Companies_Work/GearLogic_Automation/Projects/KriyoTech-CollectFlow/backend/accounts/auth.py:5)
- [Dedicated admin throttle](E:/Companies_Work/GearLogic_Automation/Projects/KriyoTech-CollectFlow/backend/admin_console/auth.py:24)
- [Frontend shared login call](E:/Companies_Work/GearLogic_Automation/Projects/KriyoTech-CollectFlow/Frontend/src/app/login/page.tsx:30)

**Fix:** Apply consistent rate limits across all authentication routes, with account/IP controls as appropriate, and require MFA for staff sessions. This conclusion comes from the route, serializer and permission configuration; no brute-force traffic was generated.

## Other operational findings

- **P2 — Only the first 25 invoices appear in the invoice page/board.** The API paginates at 25 and the page reads only the first `data.results`, without following `next` or exposing page controls. Older work and extraction failures can be hidden. [Frontend load](E:/Companies_Work/GearLogic_Automation/Projects/KriyoTech-CollectFlow/Frontend/src/app/invoices/page.tsx:16), [API pagination](E:/Companies_Work/GearLogic_Automation/Projects/KriyoTech-CollectFlow/backend/config/settings.py:71).
- **P2 — One development worker is a bottleneck.** The launcher uses Celery solo and the default queue for extraction, ERP imports and maintenance. Long external ERP calls can delay invoice extraction and heartbeat/recovery tasks. Separate queues/workers and load tests are needed before increasing client volume. This is an architectural capacity risk; no load test was run.
- **Deployment blocker — Current local settings are unsuitable for unchanged public deployment.** `check --deploy` reported W004 (HSTS), W008 (HTTPS redirect), W012 (secure session cookie), W016 (secure CSRF cookie) and W018 (DEBUG). Local DEBUG mode is not itself an incident; deploying it publicly would expose diagnostic detail. HTTPS configuration may also be enforced at a proxy, which was not inspected.
- **Recovery not verified.** Documents use local MEDIA_ROOT; DOCUMENT_STORAGE is declared but no cloud storage backend is configured in inspected settings. A database/document backup and restore drill was not demonstrated. This does not establish whether external/manual backups exist.
- **Historical frontend cache failure.** The frontend error log contains a Next manifest JSON parse failure. Its root cause and current reproducibility were not established, so it is not counted as a confirmed current crash. Avoid sharing one `.next` directory between concurrent build/dev processes when investigating it.
- **Expected access denial, not a crash:** The current ERP page generated 403 responses while the ordinary auth profile returned 200. ERP access is plan/role gated. Confirm the company's API entitlement rather than treating that denial as a server crash. No entitlement was changed during this review.

## Verification and limits

- Existing backend suite on isolated SQLite: **132 passed initially; one setup error** from sandbox temporary-directory permissions. The affected invoice extraction/approval/payment workflow test was rerun outside the sandbox and **passed**. Total existing tests passed: **133**.
- Frontend suite: **10 passed** across three files. TypeScript check passed.
- Four additional diagnostic repros confirmed the cross-company source leak, pre-approval payment, posted invoice mutation and fleet alerts crash. These repros intentionally assert the observed bad behavior; their passing does not mean the product is secure.
- Local PostgreSQL read-only probe confirmed the nullable joined-row locking error.
- Deployment check produced the five warnings listed above.
- Repro scripts are under `.dev-runtime/audit_risk_repros.py` and `.dev-runtime/audit_pg_probe.py`; they are not part of the ordinary backend test collection. Synthetic data was created only in the test database and isolated temporary media folders.
- No application fixes, real invoice payments, ERP writes or customer-record changes were performed. The review did not cover a full manual browser journey for every role, real external-provider round trips, production infrastructure, concurrency load, penetration testing or a backup restoration.

## Recommended repair sequence

1. Fix tenant-scoped invoice relationships and add cross-company API regression tests.
2. Fix PostgreSQL lock targets and fleet alert iteration; verify trip start, delivery, proof, customer billing and alerts on PostgreSQL.
3. Centralize payment readiness, immutable posted-record policy, locked balance calculation and replay handling across manual and ERP paths.
4. Implement real branch enforcement or remove security claims from metadata-only branch settings.
5. Protect all staff authentication routes and add MFA.
6. Add invoice pagination and explicit partial-load failures.
7. Complete production service supervision, queue separation, HTTPS/security settings, and tested database/document recovery.
