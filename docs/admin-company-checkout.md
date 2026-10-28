# Collect a company subscription payment in Admin

1. Open Admin → Companies → Onboard company.
2. Enter company and owner details, select Starter or another priced plan, and select the billing cycle.
3. Select **Collect payment now · Razorpay**. The form shows the configured amount due.
4. Click **Create company & open Razorpay** and complete checkout.
5. After server verification, the subscription becomes ACTIVE, the payment becomes PAID in Admin → Payments, and a paid billing invoice is generated.

**Start with trial** and **Collect payment later** remain available. Collect now creates an ONBOARDING subscription without a trial. This flow collects a single subscription period; it does not establish recurring card debits.

## Interrupted checkout

The company is saved before checkout starts. Do not create it again. Use **Collect payment** beside the company, or **Resume Razorpay payment** in the payment panel. Pending orders are reused. If checkout returned payment details but verification was interrupted, use **Verify payment again**. Check Payments before retrying if money was debited.

An open payment panel checks the saved payment status every ten seconds, including payments confirmed by a webhook. Company status refreshes after payment confirmation.

## Configuration

Set backend `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET`. A test key opens the Razorpay test checkout; use live credentials for real collections. Do not put the secret in frontend variables.

For confirmation when the browser closes, configure the public HTTPS webhook endpoint in Razorpay:

`/api/v1/billing/razorpay/webhook`

Set its matching secret in backend `RAZORPAY_WEBHOOK_SECRET`, subscribe to `payment.captured`, `payment.failed`, and `order.paid`, and run Redis and the Celery worker. Configure automatic payment capture in Razorpay; an authorized payment alone does not activate a subscription. Restart backend and worker after changing environment settings. Localhost requires a publicly reachable HTTPS forwarding address for webhook delivery.

The server calculates the price from the selected plan and cycle. It validates the checkout signature and independently fetches the captured payment to confirm the order, payment ID, amount and currency. Duplicate callbacks and captured webhooks do not extend the subscription twice. Late failed-attempt events cannot downgrade a paid payment.

Admin checkout endpoints allow active SUPER_ADMIN, ADMIN and BILLING_ADMIN staff. Tenant users and support staff cannot use them.

## Verification

The admin payment API tests passed with Razorpay network calls stubbed, including initial onboarding, pending order reuse, rejected signatures/amounts, company isolation, role restrictions, duplicate confirmation, renewal date handling and late failure events. Frontend TypeScript validation passed. No live charge was performed.

Razorpay integration reference: https://razorpay.com/docs/payments/payment-gateway/web-integration/standard/integration-steps/
