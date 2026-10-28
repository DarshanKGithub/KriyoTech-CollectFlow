# KriyoPay — incremental implementation tracker

Updated: 26 October 2026 (Asia/Calcutta).

## Authorized scope

The user requested implementation step by step from KRIYOPAY_DEVELOPMENT_PROMPTS.md.

On 26 October the user selected **both** settlement domains with separate account access:

1. KriyoPay subscription collections, administered through the platform billing control plane.
2. Each client company's merchant settlements, accessed only through its authorized workspace/account.

Platform Razorpay credentials must never become a fallback for a client merchant account. No live gateway operations are authorized by this development task.

## Stages

| Stage | State | Completion / gate |
| --- | --- | --- |
| Audit/comparison | Completed snapshot | KRIYOPAY_PROMPT_COMPARISON.md documents the 25 October baseline and twelve roadmap capabilities. |
| Prompt 1: foundation | Implemented and tested | Webhook recovery, refund intents, balances and reconciliation safeguards; 177 PostgreSQL and 18 frontend tests passed. See foundation-reliability.md. |
| Prompt 1 rollout | Local migration applied; service restart pending | Worker/beat must load the new code/schedule. No live provider acceptance claim. |
| Prompt 2: source/account/currency/settlements | Implemented and tested; local migrations applied | Separate platform/client accounts, private evidence, reviewed imports and provenance checks. 209 PostgreSQL and 22 frontend tests passed. See settlement-source-foundations.md. |
| Prompt 3: reconciliation/feedback | Implemented and tested; local migration applied | Saved runs/candidates/decisions, full server lists and reviewed exact internal-payment groups. 232 PostgreSQL and 25 frontend tests passed. See reconciliation-evidence-and-groups.md. |
| Prompt 4: read-only copilot | Planned | Enforce authorization and authoritative financial query tools; no arbitrary SQL or financial write tools. |
| Prompt 5: documents/investigation | Planned | Choose actual customer formats and preserve source evidence. |
| Prompt 6: rules and ML readiness | Planned | Rule-based evidence first. Predictive ML remains conditional on data/labels/evaluation. |
| Prompt 7: pilot readiness | Planned, parallel launch gate | Authorization, MFA, supervised deployment, backups/restore and measured performance. |

## Prompt 2 delivered scope

Delivered implementation is documented in [settlement-source-foundations.md](settlement-source-foundations.md). The following principles guided this stage:

- Represent provider/account ownership explicitly. A platform account is managed only by billing administrators; a client account is bound to exactly one tenant and its authorized finance users.
- Keep credential resolution separate by ownership scope. Prefer separate platform/client account storage or equivalent database constraints so a null tenant cannot accidentally authorize global access.
- Add account/currency provenance to supported source records. Backfill only known facts; unknown legacy account/currency must remain reviewable and excluded from unsupported matching.
- Retain protected original import files and hashes with batch/row provenance and access checks.
- Create reviewed settlement/refund import batches before enabling live provider fetches. Preserve explicit gross, fees, tax, refunds, adjustments, net and source dates, with unknown values distinct from zero.
- Build platform and tenant import endpoints on their respective existing permission surfaces. Prove cross-scope denial and tenant isolation in tests.
- Reuse current parser limits, exact decimals, audit logs, staging conventions and background infrastructure.
- Make imports repeatable without duplicate facts. Corrections/reversals must preserve the original observations.
- Do not link a settlement solely by a coincidental amount total.

Acceptance tests: both ownership scopes; foreign tenant/account denial; absent credentials never falling back; unknown legacy provenance; mismatched currency; duplicate/conflicting files and provider IDs; invalid/oversized input; exact component arithmetic; preserved source evidence; no live provider calls.

No advanced ML, vector store or graph infrastructure is required for this stage.

Local settlement, payments, fleet and phase3 migrations were applied on 26 October. No assumed source-account/currency backfill or live gateway operations were performed. A pre-existing accounts.0004 role-choice migration was outside these scoped migration commands and remains pending locally.

Prompt 3 is now delivered in [reconciliation-evidence-and-groups.md](reconciliation-evidence-and-groups.md). The existing single-record workflow is preserved alongside reviewed split/combined internal cash-payment groups. Nonzero gateway components, partial targets and many-to-many matching remain unsupported. Gateway live ingestion remains disabled. Historical and newly recorded operational payments still need explicit source verification before bank matching; their entry forms do not infer provenance.

Next stage: Prompt 4, a read-only finance assistant using authorized deterministic query services. No financial write tools, arbitrary SQL or external AI processing should be enabled by default.
