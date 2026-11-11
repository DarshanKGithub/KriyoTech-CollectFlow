# Admin Test Plan

Verify tenant-only JWTs receive 403 for all admin APIs; internal role gates; onboarding creates isolated tenant/owner/trial/subscription and audit row; cross-tenant identifiers are rejected; plans and entitlements resolve with expiry; lifecycle changes require reasons and audit; audit has no mutation API; payment configuration absence cannot activate subscriptions. Integration suite additionally covers Razorpay signatures/idempotency, email invite delivery, 2FA, limits, and scheduled lifecycle tasks before launch.
