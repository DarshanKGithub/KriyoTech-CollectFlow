# Tally Export Specification

## MVP CSV

Export only approved invoices with no open blocking exceptions. CSV uses UTF-8, comma delimiter, one detail row per invoice line, and a stable header:

`Voucher Type, Invoice Number, Invoice Date, Vendor Ledger, Purchase Ledger, GST Ledger, TDS Ledger, Item, Quantity, Rate, Taxable Value, GST Rate, GST Amount, TDS Amount, Total Debit, Total Credit`

Voucher type and ledger labels use tenant-owned Tally mappings configured at `/exports/settings`, with safe fallbacks until a mapping is added. Vendor ledgers map by vendor ID; purchase ledgers map by invoice category or `default`; GST ledgers map by GST rate or `default`; TDS ledgers map by the human-reviewed TDS section or `default`; cost centers map by vendor/category or `default`. The CSV includes a Cost Center column. Mapping changes are audited and apply only to future exports.

Dates use `YYYY-MM-DD`; monetary values use decimal notation without locale grouping. Each voucher's debit and credit totals must balance. The voucher gross is taxable value plus GST; net payable plus TDS withheld must equal that gross. Pilot accountants must map ledger labels and validate import into their Tally configuration before live use. This is a data interchange CSV, not direct Tally integration.

## Future XML integration

Add a serializer adapter that consumes approved invoice domain records and emits Tally XML. Keep eligibility checks, ledger mapping, audit, and approval rules in domain services. XML posting, response parsing, idempotency, and integration tests must be implemented and verified before describing direct integration as available.
