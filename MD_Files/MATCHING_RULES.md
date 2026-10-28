# KriyoPay Three-Way Matching Rules

## Principles

Matching is deterministic, explainable, and versioned. AI extraction supplies candidate values only; it never approves, resolves exceptions, or changes tolerances. Matching compares invoice lines to approved vendor/PO/GRN evidence. Store inputs, rules version, comparison outcomes, and calculated variances in each `MatchResult`.

## Phase 2 status and planned capabilities

- **Implemented MVP:** tenant-scoped exact vendor/PO/GRN matching, line checks, matching tolerance settings, duplicate checksum/invoice-number flags, and blocking exceptions.
- **Phase 2 implemented:** vendor aliases and confidence-scored matching; exact/file/near-duplicate candidates with human decisions; percentage and absolute rate/quantity tolerances, tax percentage tolerance, configurable vendor signal order, partial GRN policy, and service-acceptance evidence; policy-based approval and strict opt-in auto-approval eligibility.
- **Remaining matching limits:** freight/service line-to-evidence reconciliation beyond GRN service-acceptance flags is future work. Auto-approval eligibility is rule and vendor/amount scoped; it cannot clear exceptions or pending duplicate decisions.
- **Future/out of scope:** fuzzy description matching that silently passes, model-driven approval, and automatic payment release.

## Normalization

- Normalize GSTIN to uppercase without whitespace; validate format before relying on it.
- Normalize invoice, PO, and vendor names using trimmed/case-folded text and conservative punctuation/whitespace cleanup. Preserve original display values. Do not fuzzy-match ambiguous records automatically.
- Normalize item codes similarly; use configured aliases only when explicitly maintained. Description similarity can suggest a candidate but cannot silently establish a passing match.
- Compare dates as local business dates; compare money at currency precision and quantities/rates at configured precision.

## Vendor and PO matching

1. Resolve vendor by tenant-scoped vendor ID when explicitly selected; otherwise exact GSTIN, then exact normalized approved vendor name. If zero candidates, raise `VENDOR_NOT_APPROVED` when a known unapproved vendor is identified, otherwise `MANUAL_REVIEW`.
2. Resolve PO using invoice PO number, resolved vendor, and tenant. Missing PO number or no matching PO raises `MISSING_PO`. Conflicting supplier/PO association is blocking and requires manual review.
3. Map invoice line to PO line by exact item code/alias, then a unique normalized description candidate. Multiple candidates or no defensible candidate raises `MANUAL_REVIEW`.

## GRN and quantity rules

- Link GRN lines to PO lines and sum received quantity for the matched PO line, excluding cancelled/voided GRNs.
- Compare cumulative invoiced quantity to received quantity and ordered quantity. Over-billing beyond received quantity raises blocking `QTY_OVER_INVOICE`; invoiced quantity below PO line quantity can be normal partial invoicing and does not alone fail, but an incomplete receipt can raise informational/warning `PARTIAL_DELIVERY`.
- If no valid GRN exists for a matched PO line, raise blocking `MISSING_GRN` unless tenant policy explicitly allows invoice processing before receipt; such a policy must not silently mark the invoice payment-ready.
- Excess invoice quantity over PO ordered quantity raises `QTY_OVER_INVOICE`; quantity below invoice/expected amounts raises `QTY_UNDER_INVOICE` only when it indicates inconsistent units/values under configured policy. Include expected and observed values in details.

## Rate, tax, and TDS

- Rate variance is `abs(invoice_rate - po_rate) / max(abs(po_rate), epsilon)`. Compare to tenant percentage and absolute tolerances; if either configured tolerance is exceeded, create blocking `RATE_VARIANCE`.
- Recompute expected taxable amount from quantity × rate with documented rounding; compare to invoice taxable value using configured absolute tolerance. Preserve both reported and computed values.
- Calculate expected GST from taxable value and PO/tax setup where known. A GST rate or amount beyond configured tolerance raises `TAX_MISMATCH`. Missing/ambiguous tax configuration requires `MANUAL_REVIEW`, not a guessed pass.
- TDS is a review item, not a universal tax calculation. If present, compare to tenant/vendor rule when configured; otherwise raise `TDS_REVIEW` (warning or blocking per tenant policy). Never invent a deduction rate.

## Duplicate rules

- Always flag identical SHA-256 document checksum within a tenant as `DUPLICATE_INVOICE` candidate.
- Also compare normalized `(tenant, vendor, invoice_number)` across invoices. A matching key with a different file is still a duplicate candidate and requires user review; do not discard the new document.
- Duplicate candidates are blocking until reviewed/resolved. All duplicate relationships and resolution rationale are auditable.

## Exception catalog and default severity

| Code | Default severity | Blocking by default | Trigger |
| --- | --- | --- | --- |
| `DUPLICATE_INVOICE` | High | Yes | Checksum or vendor/invoice-number duplicate candidate |
| `QTY_OVER_INVOICE` | High | Yes | Invoiced quantity exceeds received/ordered quantity beyond tolerance |
| `QTY_UNDER_INVOICE` | Medium | Configurable | Material quantity inconsistency or short invoice per policy |
| `RATE_VARIANCE` | High | Yes | Rate variance exceeds tenant tolerance |
| `MISSING_PO` | High | Yes | No unambiguous tenant/vendor PO match |
| `MISSING_GRN` | High | Yes | No qualifying receipt for billed line |
| `TAX_MISMATCH` | High | Yes | GST rate/amount variance exceeds tolerance or conflicts with known setup |
| `TDS_REVIEW` | Medium | Configurable | TDS present or expected but needs policy/accountant review |
| `VENDOR_NOT_APPROVED` | High | Yes | Vendor is unapproved or cannot be verified |
| `PARTIAL_DELIVERY` | Low | No by default | PO quantity not fully received; line may be legitimately partially invoiced |
| `MANUAL_REVIEW` | Medium | Yes | Ambiguous supplier/item/source mapping, low-confidence required data, or unsupported case |

Tenant settings may tighten tolerances and make warning rules blocking. They cannot make duplicate, unapproved vendor, missing source evidence, or ambiguous mappings silently pass without an explicit audited override policy.

## Phase 2 configurable matching

Settings are tenant-specific, validated, versioned, and snapshotted on each run. Rate and tax may use percentage and/or absolute tolerances; quantity may use percentage and/or absolute units. A match priority may choose candidates in the order `PO_NUMBER`, `SUPPLIER_ITEM`, `ITEM_CODE`, `HSN_SAC`, `FUZZY_DESCRIPTION`. Fuzzy description returns suggestions only unless a unique high-confidence policy is configured and audited; it must not hide missing evidence.

Support cumulative invoicing and receipts by comparing total invoiced/received quantities per PO line across tenant invoices/GRNs, while preventing one receipt from being consumed twice beyond configured policy. An invoice can allocate lines across multiple PO lines/POs only with explicit links and an explainable allocation. Partial invoices and partial GRNs are allowed when cumulative limits are respected. Service invoices require delivery/work-completion/acceptance evidence or a reasoned manual approval rule; freight records may use shipment, LR, AWB, container, route, or rate-contract references.

Duplicate signals are independent of matching: exact vendor + normalized invoice number + amount, exact file checksum, and near-duplicate score from invoice-number edit distance, amount/date distance, and line signature. Scores/reasons are persisted. Every non-clear candidate blocks payment-ready until a user records a reasoned duplicate decision. An automated score is never a final duplicate decision.

## Invoice outcome rules

- `MATCHED` only when each invoice line has an unambiguous PO and GRN match, required comparisons pass, and no blocking exception is open.
- `EXCEPTION` when any blocking exception is open or a required source/mapping is missing.
- `PAYMENT_READY` requires an approved invoice version, completed passing match, no open blocking exception, and valid totals.
- Any edit to invoice content increments invoice version and invalidates prior approval/match for payment readiness; rerun matching and approval as needed.
- Resolving an exception records note and actor. Overriding a blocking exception records mandatory reason, original values, linked evidence, and approver/role if policy requires it.

## Explainability and examples

Each line comparison includes invoice line ID, PO line ID, GRN line IDs, matched by fields, ordered/received/invoiced quantities, expected/observed rate, tax values, tolerances applied, pass/fail, and exception codes. Missing or conflicting evidence should be reported as explicit exceptions, never hidden by a global match score.
