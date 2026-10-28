# KriyoPay product UX

## Product promise

Help finance teams move each supplier invoice from arrival to a confident, approved, reconciled payment record. Make the next safe action obvious, explain what needs attention, and keep the underlying invoice evidence close at hand.

## UX principles

1. **Lead with work, not configuration.** Put Overview, Invoices, Exceptions, Approvals, and Payments first. Keep rules and setup tools grouped under Controls and Administration.
2. **One clear next step.** Every queue should explain why a record is here and provide the next permitted action beside it.
3. **Use plain language.** Prefer “Needs review”, “Waiting for approval”, “Ready to export”, and “Could not connect” over raw status codes, framework errors, or generic “Failed” messages.
4. **Show real state honestly.** Distinguish loading, empty, success, warning, and error states. Never show sample activity as live workspace data. Give connection failures a retry path and explain that data was not loaded.
5. **Make financial actions deliberate.** Show amount, supplier, invoice reference, and consequences before approve, reject, send, allocate, or export. Record decisions and make confirmations clear.
6. **Keep context visible.** Show the active workspace, signed-in user, role, and current section consistently. Every record view should make it easy to return to its queue.
7. **Design for keyboard and small screens.** Use semantic headings and labels, visible focus, accessible names, touch-sized controls, responsive navigation, and tables that can scroll without clipping.

## Information architecture

### Daily work

- Overview
- Invoices
- Exceptions
- Approvals
- Payments
- Vendors

### Procurement and records

- Purchase orders
- Goods received
- Financial notes
- Duplicate review
- Tally export
- Audit log

### Controls

- Email intake
- Approval rules
- SLA rules
- Follow-up drafts
- Vendor aliases
- Custom fields
- Bulk actions
- Reports
- Notifications

### Administration

- Users and roles
- Settings

Daily work remains visible in the primary navigation. Less frequent tools are grouped and collapsible; the current page’s group opens automatically.

## Core journeys

### Sign in and connect

After sign-in, land on the live workspace overview. If the API is unreachable or credentials have expired, explain the problem in a calm banner with a retry or sign-in action. Do not leave the user with an unexplained blank page or browser error.

### Process an invoice

1. Upload a PDF or image and show file name, size, supported types, and upload progress.
2. Confirm that the invoice was received and explain that fields need review when extraction is manual or uncertain.
3. Keep supplier, invoice number, date, amount, and line items together in review.
4. Explain match results and exceptions in plain terms, with evidence and a direct resolution action.
5. Show the current approval step and approver before submission.
6. After approval, show the outstanding amount and next payment/export action.

### Resolve exceptions and approvals

Queues explain why an item is blocked, its age or due date, who owns it, and the next action. Empty queues celebrate completion and point to a useful destination. Reject, override, and financial decisions request a reason where required and confirm the saved outcome.

## Interaction and content rules

- Use one primary action per screen and visually quieter secondary actions.
- Keep filters and search close to the queue they control. Preserve filters while opening and returning from a record when practical.
- Confirm destructive or externally visible actions. Sending vendor email must remain an explicit user action.
- Use inline validation next to the field and preserve valid user input after recoverable errors.
- Success messages state what changed; errors state what happened and how to recover.
- Format currency in INR consistently and display dates in a human-readable local format while retaining exact dates in forms.
- Replace raw JSON, database values, and internal enum strings with readable labels and structured details.
- Loading controls indicate progress and prevent duplicate submissions. Empty states explain what belongs in the section and how to create the first item.

## Visual and accessibility direction

- Retain KriyoPay’s forest-green and mint identity, white surfaces, quiet borders, and high-contrast body text.
- Use consistent page titles, short descriptions, spacing, button styles, status badges, and table density.
- Use color with text and icons; never communicate status by color alone.
- Maintain visible keyboard focus, logical tab order, semantic table headers, form labels, and `aria-live` status feedback.
- Provide a compact mobile header and an accessible navigation drawer; avoid hiding essential destinations on narrow screens.

## UX acceptance checklist

- A signed-in user can tell which workspace and section they are in.
- Primary work queues are reachable without expanding secondary navigation.
- Every async screen has loading, success, error, and useful empty states.
- API errors do not appear as raw `Failed to fetch` messages without recovery guidance.
- Financial and external actions have clear context, permission checks, and a visible result.
- Pages remain usable at mobile widths and with keyboard-only navigation.
- No static/demo records are presented as real workspace data.
# Phase 3 surfaces

- Tax review (`/compliance`) groups invoices with tax totals and screening flags. Reviewers record supplier status evidence, ITC decision/reason, TDS section/rate and certificate reference. The interface labels local checks as screening and avoids presenting them as government validation.
- Bank reconciliation (`/bank-reconciliation`) begins with CSV header mapping, then shows imported rows and their state. A finance user links an exact-amount payment and separately confirms reconciliation. Imported rows never become reconciled automatically.
- Purchase order drafts (`/purchase-orders`) support multiple lines, draft edits with a mandatory reason, and a revision history that preserves each prior vendor/date/line snapshot. Submitted and approved POs remain locked.
- Vendor portal management (`/vendor-portal`) creates and revokes expiring vendor-specific links. The shareable token is displayed only at creation. Suppliers use `/portal/{token}` to submit invoices, view only their own invoice statuses, and ask invoice-specific questions.
- AI invoice review (`/ai-review`) lets an owner select a configured OpenAI or Gemini provider and enable workspace review. A finance user's per-request confirmation is required. It sends invoice metadata and up to 50 line items but not the source file; users can keep/dismiss suggestions. Model confidence is labeled uncalibrated.
- Users with active memberships in multiple company workspaces can switch between them from the sidebar. The switch changes the selected tenant; it does not grant branch-level access.
- Branches (`/branches`) lets company owners maintain branch records, activate/deactivate non-default branches, and assign workspace members. The page clearly states that assignment metadata is not yet used to filter invoices, vendors, POs, GRNs, or payments.
- Integrations (`/integrations`) shows one-time API keys and webhook signing secrets only at creation, supports key revocation and endpoint pause, and queues delivery tests. Owners/finance can inspect recent delivery attempts and manually retry a failed event up to three cycles after checking their receiver. The event ID stays unchanged for deduplication; the user is told when the automatic delivery worker must be run.
- Gmail account connection requests read-only access and verified identity. The page never receives OAuth client secrets or refresh tokens; it clearly states that mailbox synchronization is not enabled yet.
- WhatsApp (`/whatsapp`) includes a consent register with evidence notes. A saved opt-in is required to draft messages, and inbound opt-out keywords prevent later sends.
- An uncertain WhatsApp send remains unresolved until a finance user checks Meta WhatsApp Manager and records evidence plus the message ID or confirms non-delivery. The interface does not retry uncertain sends.
- Workspace sign in asks for email/password only, then discovers memberships and prompts users who belong to multiple companies to choose one. New company workspaces are created by the internal admin and owners join through an emailed invitation; public self-signup is disabled.
- Internal staff use a separate modern sign-in at `/admin-login`. A first-run operator command creates the first Super Admin and prints a generated password once; tenant membership does not grant internal access.

# Tally export setup

Workspace finance users can open **Configure ledger mappings** from the Tally export page. The mapping form accepts a Tally name for vendor, purchase category, GST rate, TDS section, voucher type, and cost center dimensions. It preserves readable fallback labels until configured and only affects future CSV files. The app does not connect to or post data directly into a customer's Tally company.
