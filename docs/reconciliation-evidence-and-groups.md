# Step 3 — Reviewed reconciliation evidence and allocation groups

Implemented: 26 October 2026. Extends the existing bank reconciliation API and MUI screen; no new matching application, gateway operation or AI provider was introduced.

## Delivered

### Saved matching evidence

- Matching runs retain bank source snapshots, input fingerprints, rule version `bank-exact-v2`, ambiguity and bounded-search indicators.
- Saved candidates retain original and normalized references, exact amount/date/account/currency evidence, stable reason codes, rank and heuristic score.
- Repeating suggestions on unchanged inputs reuses the run/candidates. Changed financial/reference/eligibility evidence produces a new run. Prior evidence is retained.
- Unicode NFKC/case/punctuation normalization supports varied reference formatting. Exact normalized references rank ahead of amount/date/narration hints. Substring references no longer count as stable identifier matches.
- Candidate search requires known active workspace bank account/currency, transaction direction, equal amount and dates within seven days. Cancelled supplier payments, reversed driver payments and already claimed targets are excluded.
- Queries consider at most 100 eligible records per supported target type and retain/display the best 20 candidates. Candidate/display limits are explicit. More than one eligible candidate remains ambiguous; the UI warns the reviewer.
- The system does not perform fuzzy matching, calibrated probability estimation or automatic confirmation. Scores and legacy HIGH/MEDIUM/LOW compatibility fields are rule hints only.

### Reviewer decisions and corrections

- Accept, reject, confirm and clear decisions retain actor, timestamp, reason, source/target snapshots and candidate evidence where applicable.
- Rejecting a saved candidate requires an explicit reason and stable request key; it leaves the bank/payment records unchanged. The candidate remains visible as rejected.
- Candidate acceptance checks that its run and target facts are current. A rejected candidate cannot be accepted through the same saved candidate action; a manual override requires an explicit reason.
- Clearing a link requires a correction reason. Original review events are retained; bank links can change without rewriting the recorded payment itself.
- Bank row revisions protect the current UI against stale actions. Single-record API revision/request-key fields remain optional for older clients; the current UI supplies them. Group revisions are mandatory at confirmation/clear.
- A repeated request key with the same payload returns the recorded result. Reusing it for different evidence returns 409. A replay returns the original action result; refresh the list for current state after later actions.
- The MUI transaction drawer provides paginated review history and readable evidence. Earlier activity remains in the existing workspace audit log; historical matching decisions are not invented/backfilled.

### Reviewed split and combined payment groups

Supported:

1. One bank row against several complete internal payments/collections.
2. Several bank rows against one complete internal payment/collection.

Both sides are bounded to ten members, and only one side may contain multiple members. Supplier payments, driver salary payments and customer collections retain their existing finance scope. The UI selects one target type per group; the API also permits compatible debit target types together when all evidence agrees.

Every member must satisfy:

- Same verified active workspace bank account and currency, with the correct debit/credit direction.
- An exact shared normalized transfer reference of at least four characters. Amount totals alone are insufficient.
- Target dates within seven days of every bank member.
- Exact total equality, with every target allocated in full and no already claimed member.
- Explicit `fees`, `fee_tax`, `refunds` and `adjustments`, each equal to the decimal string `0.00` for these internal cash-payment groups. Unknown values and nonzero gateway components are rejected.

In **Reconciliation center → Review transaction → Match split or combined payments**, enter the record IDs, verify the component evidence and give a reason. Preview shows every member and both totals. A separate acknowledgment records the group as MATCHED. Confirming the complete group is another reviewed action.

Preview does not create a financial group. The current UI sends its evidence hash when recording the group, so changed evidence requires another preview. Confirmation revalidates all source/target facts and rejects cancelled/reversed targets or other stale evidence. Clearing a group releases every member together and preserves its original evidence/history. Individual member rows cannot be independently changed while grouped.

Workspace reconciliation writes share a short tenant lock before bank/target claims. Database uniqueness constraints protect active group targets; the same service checks legacy single links and group claims under that shared lock. There are no remote calls inside these matching transactions. This serializes reconciliation writes within a workspace; production throughput has not been load-tested.

Not supported in this stage: many-to-many groups, partial target allocations, tolerance-based differences, inferred components, nonzero gateway fee netting, FX, settlement-to-bank group matching, automatic subset search or automatic posting. These need additional accounting evidence and explicit account relationships.

## Complete lists and totals

- Bank lists now use server-side pagination, search, status/direction/date/account filters and allowlisted sorting. `count` covers every filtered record; workspace status counts are calculated independently across all imported rows.
- Default bank page size is 25; supported sizes are 10/25/50/100. The response preserves `transactions` and `counts`, and adds `count`, `page`, `page_size` and `has_next`. External consumers that previously assumed the default response contained every recent row must now paginate.
- Payment register uses `/payments?paginated=1`, server pagination/search/date filtering/sorting and full filtered active-payment totals using exact database decimals. Cancelled payments are excluded from this register. These totals describe the INR operational ledger, not source currency verification or bank balances.
- The older unpaginated `/payments` array contract remains bounded to 200 for compatibility. Product register/dashboard views now use the paginated contract; external consumers should migrate to it.
- Payment details query bank links by target ID across all statements, including active group membership, instead of searching a latest-500 sample. Recent-payment dashboard cards deliberately request five active records; they are not used as all-record totals.
- Paginated payment register and reconciliation require workspace-wide finance access. Auditors can read records/history; they cannot generate suggestions, write decisions, import or confirm. Tenant source entitlements remain enforced by existing permissions. Platform billing accounts are not exposed through workspace reconciliation.

## API additions on the existing bank endpoint

Base: `/api/v1/bank-reconciliation`.

| Request | Purpose |
| --- | --- |
| GET `page`, `page_size`, `search`, `status`, `direction`, `from`, `to`, `account_id`, `sort` | Full filtered list and counts |
| GET `target_type`, `target_id` | Direct single/group target lookup |
| GET `suggestions_for=<bank_uuid>` | Reuse/create saved matching evidence for finance reviewers |
| GET `history_for=<bank_uuid>&history_page=1` | Paginated retained review decisions, including cleared groups |
| GET `group_for=<group_uuid>` | Authorized group evidence/status/revision |
| PATCH `match`, `reconcile`, `unmatch` | Existing single-record actions with saved review history |
| PATCH `reject_candidate` | Retain rejection with `candidate_id`, `reason`, `request_key` |
| PATCH `group_preview`, `group_match` | Validate/record bounded exact groups |
| PATCH `group_confirm`, `group_clear` | Review the complete group using `group_id`, `expected_revision`, reason and request key |

Single actions use `transaction_id`; candidate acceptance additionally supplies `candidate_id` and the target identity. New UI requests use `expected_revision` and stable UUID `request_key`. Group creation uses `bank_ids`, `targets`, explicit zero `components`, reason/request key and the preview hash. Cross-tenant resources are not readable/usable; invalid or competing claims fail without partial posting.

## Synthetic evaluation

Test: `phase3/test_reconciliation.py::test_labeled_rule_evaluation`.

Twelve hand-labeled synthetic cases: four varied-format exact references, two true pairs with missing references, two true pairs with competing records, and four negatives with wrong date/account/currency or cancellation. Labels come from deliberately constructed fixture identities, not reviewer-labeled customer history. Evaluation policy recommends only a unique exact normalized-reference candidate. Actual reconciliation still requires human acceptance and confirmation in every case.

| Metric | Result |
| --- | --- |
| True positives / false positives / false negatives / true negatives | 4 / 0 / 4 / 4 |
| Recommendation precision | 100% (4/4) |
| Recommendation recall | 50% (4/8) |
| False-match rate among recommendations | 0% (0/4) |
| Cases with no eligible candidates | 33.3% (4/12) |
| Cases needing review without a unique exact-reference recommendation | 66.7% (8/12) |

This tiny fixture set verifies deterministic behavior and conservative handling of ambiguity. It does not establish production accuracy, calibration or fraud detection. No fuzzy scorer was added without customer labels and evidence of improvement.

## Files, migration and rollout

- `backend/phase3/models.py`: run/candidate/review/group/member/claim models and bank revision/group fields.
- `backend/phase3/reconciliation.py`: deterministic evidence, full-list queries, reviewed single/group services and shared claim locking.
- `backend/phase3/views.py`: existing bank endpoint delegates to those services; source import/download flows are preserved.
- `backend/invoices/phase2.py`, `backend/payments/serializers.py`: paginated active-payment register and vendor names.
- `Frontend/src/app/bank-reconciliation/page.tsx`: server lists, saved candidate feedback, corrections and embedded group/history controls.
- `Frontend/src/components/reconciliation-groups.tsx`, `reconciliation-history.tsx`: MUI group preview/decisions and readable evidence.
- `Frontend/src/components/payment-register-grid.tsx`, `transaction-details.tsx`, `financial-dashboard.tsx`, `Frontend/src/app/payments/page.tsx`: complete register, direct bank-link lookup and bounded recent-card data.
- `Frontend/src/lib/finance.ts`: new response metadata and readable validation-array errors.
- Regression coverage: `backend/phase3/test_reconciliation.py`, frontend group/page/finance tests.

Applied successfully to the local database on 26 October: `phase3.0014_banktransaction_revision_reconciliationgroup_and_more`. It adds tables/constraints and nullable group/default-zero revision fields. It does not alter historical financial amounts or assign assumed matching evidence.

~~~powershell
# From backend, after deploying the matching source:
.\.venv\Scripts\python.exe manage.py migrate phase3 --noinput
~~~

Reload the backend/frontend after deployment. Existing Step 1 worker/beat restart requirements remain; Step 3 adds no provider synchronization job. Direct database operators can bypass application immutability policies; this is not a claim of a tamper-proof ledger.

## Verification

- Complete isolated PostgreSQL suite: **232 passed**, no skips. Includes concurrent legacy/group claims, both split/combined shapes, customer credits, driver reversal/cancellation checks, stale preview/revision/candidate rejection, scoped history and lists beyond 200/500 records.
- Frontend suite: **25 passed** across eight files; TypeScript and ESLint passed.
- Production build generated **64 pages**. Subsequent candidate warnings and validation-message handling were checked again by type/lint/tests.
- Django system check and migration drift check passed. Sandbox migration-history/build checks initially hit Windows permissions; the required checks/build were rerun with permission.
- Tests used unique PostgreSQL databases, temporary files, in-memory Celery and blocked external urllib HTTP. No live gateway, refund, payment or external messaging operation was triggered.
- Production browser workflows, operational throughput, customer-reference quality and real merchant settlement reconciliation remain unverified. The implementation is an incremental foundation, not production launch certification.
