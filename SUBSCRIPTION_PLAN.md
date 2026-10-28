# Subscription Plans

Plan prices and limits are database configuration, never frontend constants. Seed defaults: Trial ₹0/20 invoices/2 users; Starter ₹7,500 monthly/₹75,000 annual/100 invoices/3 users; Growth ₹15,000/₹150,000/400/10; Control ₹30,000/₹300,000/1,200/read-only unlimited; Enterprise custom. Currency defaults to INR. Quarterly pricing can be configured independently.

Subscription periods store plan, cycle, status, start/end, next billing, trial end, grace period, and auto-renew. Treat amounts as minor units (paise); show formatting only at presentation. Enterprise custom amounts may be null.
