# Automatic invoice workflow

## What happens

New uploads use the existing extraction queue. When extraction finishes, a separate durable workflow validates the invoice, links a unique workspace supplier by GSTIN, runs the existing matching engine, and submits approval automatically. Saving reviewed corrections also queues this workflow, without requiring Run match or Submit approval clicks.

The default is enabled for new workflows. Owners and finance users can pause it in Settings → Automatic invoice workflow. Existing invoices are not bulk processed: use Resume automation on an eligible invoice.

## Automatic checks

- Current workspace subscription, plan access, company overrides and workflow setting.
- Required extraction header fields meet the configured confidence threshold (default 90%). Model confidence is not a guarantee of accuracy. A person may instead review and save the invoice fields.
- Invoice number/date/positive total, valid line quantities, arithmetic and GST agree within INR 0.02. Discounts, rounding differences and uncertain data require review.
- An unreviewed supplier is linked only using a unique GSTIN. No supplier or bank account is created or changed automatically. Ambiguous names are never an automatic identity decision.
- Existing PO/GRN, quantity, rate, tax and duplicate checks remain authoritative. More than 500 invoices in the supplier history requires manual duplicate review because the current matching engine has a search cap.
- Supplier must be approved. Required custom fields must be filled.
- Auto-approval requires the auto_approval entitlement plus an explicitly enabled policy naming the supplier and amount cap. Nonempty unknown condition configurations do not auto-approve. Unresolved exceptions and unresolved/confirmed duplicate checks prevent auto-approval.
- Otherwise an eligible approver is notified; the submitter cannot be that approver. No eligible approver becomes an actionable attention item.

## Reliability and history

Invoice.automation stores a run ID, invoice version, state, attempt count and readable message. Invoice row locks fence duplicate deliveries and stale versions. Matching/approval use a shared transaction-safe approval service. Approvals remain attached to their invoice version; retries do not create another approval workflow for an already submitted invoice.

Failed queue dispatch stays in the database. Celery Beat republishes queued/retry work every minute and recovers interrupted work after five minutes. A task attempts processing up to four times. Only resumable supplier/record/configuration waits are retried every five minutes; low confidence and arithmetic errors need a correction. Corrected records queue a fresh version. A permanent failure can be resumed manually.

System actions are audited and actionable failures have in-app notifications. The invoice grid and Needs attention show the stopping reason. Pause/revocation is checked when work runs.

## Operation

- Migration: invoices.0008_invoice_automation (applied locally).
- Worker: invoices.tasks.advance_invoice.
- Scheduler: invoices.tasks.maintain_invoice_workflows every 60 seconds.
- Gmail mailbox polling: phase3.tasks.sync_gmail_mailboxes every 5 minutes for active workspaces with the email intake entitlement. Polls use Gmail read-only access, dedupe by message and file checksum, and inspect up to 500 messages from the last 30 days.
- Existing extract_invoice, extraction recovery and provider retry behavior are retained.
- Restart both Celery worker and Beat after deployment; deploy the migration before running the updated code.

ERP invoice records still require a person to review and apply the mapped import. Applying an invoice queues the same matching and approval workflow, including the PO number and supplier GSTIN when provided by the ERP. Duplicate email files are routed to exception review and skip extraction. Matching exceptions notify finance/owners; PO issues also notify Purchase, while receipt or service acceptance issues notify Purchase and Store.

## Financial boundary

Automation stops at PAYMENT_READY or an assigned approval and notifies finance/owners when payment is ready. It does not transfer money or create a payment record. KriyoPay currently has no client vendor-payment transfer provider or outgoing payment policy, so a scheduled transfer cannot safely be executed. Bank reconciliation continues to produce evidence-backed candidates; a finance user confirms the match and reconciliation. The workflow does not fabricate receipts, loosen tolerances or enable a spending policy. Configure invoice auto-approval separately in Approval rules → Guarded auto-approval, with the relevant feature enabled by Super Admin.

## Checks performed

Django system checks, migration consistency check, frontend TypeScript and ESLint. No automated tests, example payments or approvals were run for this change.
