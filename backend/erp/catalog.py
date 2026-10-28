RESOURCES = {"suppliers", "purchase_orders", "receipts", "invoices", "payments"}

CATALOG = {
    "DYNAMICS_FINANCE": {
        "name": "Microsoft Dynamics 365 Finance", "mode": "OData + Microsoft Entra ID",
        "direct_write_resources": ["suppliers", "purchase_orders", "receipts", "invoices", "payments"],
        "config_fields": {"base_url": "Finance environment URL", "legal_entity": "Legal entity (dataAreaId)", "entra_tenant_id": "Microsoft Entra tenant ID", "client_id": "Application client ID"},
        "secret_fields": {"client_secret": "Application client secret"},
        "resources": ["suppliers", "purchase_orders", "receipts", "invoices", "payments"],
        "note": "Finance entity names and field mappings must be validated against your environment metadata. Business Central uses a different API.",
        "docs": "https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/data-entities/odata",
    },
    "ERPNEXT": {
        "name": "ERPNext", "mode": "Frappe REST API",
        "direct_write_resources": ["suppliers", "purchase_orders", "receipts", "invoices", "payments"],
        "config_fields": {"base_url": "ERPNext site URL", "company": "ERPNext company name"},
        "secret_fields": {"api_key": "API key", "api_secret": "API secret"},
        "resources": ["suppliers", "purchase_orders", "receipts", "invoices", "payments"],
        "note": "Use a dedicated integration user. Created accounting documents stay in draft (docstatus 0).",
        "docs": "https://docs.frappe.io/framework/user/en/api/rest",
    },
    "TALLY": {
        "name": "TallyPrime", "mode": "XML over HTTP",
        "direct_write_resources": ["suppliers", "invoices", "payments"],
        "config_fields": {"base_url": "Tally HTTP gateway URL", "company": "Exact Tally company name"},
        "secret_fields": {},
        "resources": ["suppliers", "purchase_orders", "receipts", "invoices", "payments"],
        "note": "Tally must be running with the company loaded. Local/private gateways require an operator-approved ERP_TRUSTED_ORIGINS entry. Do not expose port 9000 publicly.",
        "docs": "https://help.tallysolutions.com/developer-reference/integration-capabilities/method-specific-integration/xml/",
    },
    "ZOHO_BOOKS": {
        "name": "Zoho Books", "mode": "OAuth 2.0 with automatic access-token refresh",
        "direct_write_resources": ["suppliers", "purchase_orders", "invoices", "payments"],
        "config_fields": {"region": "Data centre (in, com, eu, com.au, jp, ca, com.cn, sa)", "organization_id": "Zoho organization ID", "client_id": "OAuth client ID"},
        "secret_fields": {"client_secret": "OAuth client secret", "refresh_token": "OAuth refresh token"},
        "resources": ["suppliers", "purchase_orders", "invoices", "payments"],
        "note": "Use the organization's data centre. Connect Zoho Inventory separately for goods receipts.",
        "docs": "https://www.zoho.com/books/api/v3/",
    },
    "ZOHO_INVENTORY": {
        "name": "Zoho Inventory", "mode": "Zoho Books companion · purchase receives",
        "config_fields": {"region": "Data centre (in, com, eu, com.au, jp, ca, com.cn, sa)", "organization_id": "Zoho Inventory organization ID", "client_id": "OAuth client ID"},
        "secret_fields": {"client_secret": "OAuth client secret", "refresh_token": "Inventory OAuth refresh token"},
        "resources": ["suppliers", "purchase_orders", "receipts"],
        "direct_write_resources": ["receipts"],
        "note": "Authorize Inventory scopes separately. Link existing local suppliers and purchase orders before receiving; do not create duplicates of Books imports. Receipt lines require purchase-order line IDs.",
        "docs": "https://www.zoho.com/inventory/api/v1/purchasereceives/",
    },
}

# Finance entities can be customized and are configured explicitly rather than
# silently assuming that a similarly named entity is present in every tenant.
FINANCE_SUGGESTIONS = {"suppliers": "VendorsV2", "purchase_orders": "PurchaseOrderHeadersV2", "invoices": "VendorInvoiceHeaders"}
