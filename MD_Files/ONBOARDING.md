# Tenant Onboarding and Pilot Checklist

## Tenant setup

1. Register company owner and unique workspace key.
2. Confirm company name, timezone, default purchase/GST/TDS ledger labels, tolerances, duplicate policy, and email intake workflow.
3. Invite finance, purchase, store, and approver users with least-privilege roles.
4. Add vendors and confirm GSTIN and approval state.

## Sample data import

Prepare UTF-8 CSV files with a header row. PO headers/lines require PO number, vendor code or GSTIN, order date, line number, item code/description, quantity, UOM, rate, and GST rate. GRN headers/lines require GRN number, PO number, received date, PO line reference, item description/code, received quantity, and UOM. Validate vendor and PO references before import; retain source workbook references.

## Pilot checklist

- [ ] Confirm tenant memberships and cross-tenant isolation.
- [ ] Import sample vendors, 10 POs, and 10 GRNs; review rejected-row feedback and unmatched records.
- [ ] Process 20 synthetic or consented invoices with 6+ exception cases including duplicate, missing GRN, and rate variance.
- [ ] Review extraction confidence and corrections; ensure manual invoice entry is usable.
- [ ] Resolve/override exceptions with notes/reasons and inspect audit records.
- [ ] Complete approval and rejection paths with the correct approver role.
- [ ] Reconcile Tally CSV voucher count and totals with the pilot accountant.
- [ ] Record review-time and line-match metrics, defects, and customer acceptance.
