# Tenant Onboarding and Pilot Checklist

## Tenant setup

1. Register company owner and unique workspace key.
2. Confirm company name, timezone, default purchase/GST/TDS ledger labels, tolerances, duplicate policy, and email intake workflow.
3. Invite finance, purchase, store, and approver users with least-privilege roles.
4. Add vendors and confirm GSTIN and approval state.

Internal staff can see invitation delivery status and reissue an unaccepted owner invitation from the company record. Delivery is retried automatically with bounded backoff; the link expires after seven days, and reissue invalidates the previous link. “Submitted” means the configured email provider accepted the message, not that it reached the inbox. The local console email backend is explicitly marked as not delivered. Celery Beat must be running to recover invitations that could not be published to the task broker.

## Sample data import

Prepare UTF-8 CSV files with a header row. PO headers/lines require PO number, vendor code or GSTIN, order date, line number, item code/description, quantity, UOM, rate, and GST rate. GRN headers/lines require GRN number, PO number, received date, PO line reference, item description/code, received quantity, and UOM. The PO and GRN screens provide downloadable templates and a non-persisting preview that reports row-level validation errors. Download rejected rows with errors, correct the source, preview again, then import only after review. Imports are limited to 5 MB and 1,000 data rows; rows are revalidated when committed because workspace records may change after preview.

## Pilot checklist

- [ ] Confirm tenant memberships and cross-tenant isolation.
- [ ] Import sample vendors, 10 POs, and 10 GRNs; review rejected-row feedback and unmatched records.
- [ ] Process 20 synthetic or consented invoices with 6+ exception cases including duplicate, missing GRN, and rate variance.
- [ ] Review extraction confidence and corrections; ensure manual invoice entry is usable.
- [ ] Resolve/override exceptions with notes/reasons and inspect audit records.
- [ ] Complete approval and rejection paths with the correct approver role.
- [ ] Reconcile Tally CSV voucher count and totals with the pilot accountant.
- [ ] Record review-time and line-match metrics, defects, and customer acceptance.

The admin company detail page tracks workspace evidence for owner activation, finance/approver membership, approved vendors, sample PO/GRN volume, invoice volume, exception coverage, and an invoice decision. It does not certify external setup, customer acceptance, or Tally reconciliation; those still require operator confirmation.
