"""Commercial grouping and independently controlled fleet capabilities."""
SOLUTIONS = ("InvoiceFlow", "Procure", "Reconcile", "SettleView", "Transport", "DriverFinance")

FEATURE_SOLUTIONS = {
    "invoice_upload": "InvoiceFlow", "ai_extraction": "InvoiceFlow", "email_invoice_intake": "InvoiceFlow",
    "duplicate_detection": "InvoiceFlow", "approval_workflow": "InvoiceFlow", "multi_level_approval": "InvoiceFlow",
    "auto_approval": "InvoiceFlow", "credit_debit_notes": "InvoiceFlow", "custom_fields": "InvoiceFlow",
    "bulk_actions": "InvoiceFlow", "tally_csv_export": "InvoiceFlow", "tally_xml_integration": "InvoiceFlow",
    "api_access": "InvoiceFlow", "advanced_reports": "InvoiceFlow", "whatsapp_intake": "InvoiceFlow",
    "sso": "InvoiceFlow", "priority_support": "InvoiceFlow", "po_grn_matching": "Procure",
    "payment_tracking": "Reconcile", "fleet_management": "Transport",
}

FLEET_FEATURES = (
    ("fleet_tracking", "Live tracking & playback", "Transport"),
    ("fleet_geofencing", "Sites & geofences", "Transport"),
    ("fleet_dispatch", "Dispatch & route planning", "Transport"),
    ("fleet_trips", "Trip management", "Transport"),
    ("fleet_assets", "Trucks & driver directory", "Transport"),
    ("fleet_fuel", "Fuel management", "Transport"),
    ("fleet_maintenance", "Maintenance & reliability", "Transport"),
    ("fleet_documents", "Vehicle & transport documents", "Transport"),
    ("fleet_orders", "Customers & transport orders", "Transport"),
    ("fleet_return_loads", "Return loads & bookings", "Transport"),
    ("fleet_docks", "Dock scheduling & detention", "Transport"),
    ("fleet_exceptions", "Alerts & exception management", "Transport"),
    ("fleet_portal", "Customer shipment portal", "Transport"),
    ("fleet_notifications", "Customer notifications", "Transport"),
    ("fleet_reports", "Operational reports & profitability", "Transport"),
    ("fleet_driver_app", "Driver workspace", "Transport"),
    ("fleet_driver_finance", "Driver salaries, advances & settlements", "DriverFinance"),
    ("fleet_customer_billing", "Customer invoices & collections", "DriverFinance"),
    ("fleet_freight_reconciliation", "Freight expense reconciliation", "DriverFinance"),
    ("settlement_review", "Settlement report review", "SettleView"),
)
FLEET_KEYS = {key for key, _, _ in FLEET_FEATURES if key.startswith("fleet_")}
STARTING_MONTHLY_PRICES = {
    "invoice_upload": 19900,
    "ai_extraction": 39900,
    "email_invoice_intake": 9900,
    "po_grn_matching": 49900,
    "duplicate_detection": 0,
    "approval_workflow": 9900,
    "multi_level_approval": 9900,
    "auto_approval": 14900,
    "payment_tracking": 49900,
    "credit_debit_notes": 9900,
    "custom_fields": 4900,
    "bulk_actions": 4900,
    "tally_csv_export": 0,
    "tally_xml_integration": 29900,
    "api_access": 29900,
    "advanced_reports": 19900,
    "whatsapp_intake": 9900,
    "sso": 49900,
    "priority_support": 29900,
    "fleet_management": 0,
    "fleet_tracking": 49900,
    "fleet_geofencing": 9900,
    "fleet_dispatch": 39900,
    "fleet_trips": 29900,
    "fleet_assets": 0,
    "fleet_fuel": 29900,
    "fleet_maintenance": 19900,
    "fleet_documents": 9900,
    "fleet_orders": 19900,
    "fleet_return_loads": 19900,
    "fleet_docks": 9900,
    "fleet_exceptions": 0,
    "fleet_portal": 9900,
    "fleet_notifications": 9900,
    "fleet_reports": 19900,
    "fleet_driver_app": 0,
    "fleet_driver_finance": 39900,
    "fleet_customer_billing": 29900,
    "fleet_freight_reconciliation": 19900,
    "settlement_review": 49900,
}


def fleet_feature_for_path(tail):
    root = tail.strip("/").split("/", 1)[0]
    groups = {
        "fleet_tracking": {"live-locations", "gps-devices", "route-integration"},
        "fleet_geofencing": {"geofences", "geofence-events"},
        "fleet_dispatch": {"dispatch-recommendations", "dispatch-plans", "driver-schedules"},
        "fleet_trips": {"trips"}, "fleet_assets": {"vehicles", "drivers"},
        "fleet_fuel": {"fuel"}, "fleet_maintenance": {"maintenance", "reliability"},
        "fleet_documents": {"vehicle-documents", "logistics-documents"},
        "fleet_orders": {"customers", "orders", "lorry-receipts"},
        "fleet_return_loads": {"return-loads", "booking-history"},
        "fleet_docks": {"docks", "dock-appointments", "detention"},
        "fleet_exceptions": {"alerts", "exceptions", "follow-ups"},
        "fleet_portal": {"shipment-links"}, "fleet_notifications": {"customer-notifications"},
        "fleet_reports": {"operational-reports", "revenue-leakage"},
        "fleet_driver_app": {"my-trips"},
        "fleet_driver_finance": {"driver-salaries", "driver-advances", "driver-pay-policies", "driver-earnings", "driver-ledger.csv", "driver-salary-adjustments"},
        "fleet_customer_billing": {"customer-invoices"},
        "fleet_freight_reconciliation": {"freight-imports", "freight-import-rows"},
    }
    if root == "trips" and tail.endswith(("/location", "/location-history", "/eta-history", "/refresh-route")):
        return "fleet_tracking"
    if root == "trips" and tail == "trips/report":
        return "fleet_reports"
    return next((key for key, roots in groups.items() if root in roots), None)
