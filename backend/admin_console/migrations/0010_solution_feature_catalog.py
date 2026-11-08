from django.db import migrations

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
    "fleet_management": 0, "fleet_tracking": 149900, "fleet_geofencing": 49900,
    "fleet_dispatch": 149900, "fleet_trips": 99900, "fleet_assets": 49900,
    "fleet_fuel": 99900, "fleet_maintenance": 79900, "fleet_documents": 49900,
    "fleet_orders": 79900, "fleet_return_loads": 79900, "fleet_docks": 49900,
    "fleet_exceptions": 49900, "fleet_portal": 79900, "fleet_notifications": 49900,
    "fleet_reports": 99900, "fleet_driver_app": 79900, "fleet_driver_finance": 149900,
    "fleet_customer_billing": 99900, "fleet_freight_reconciliation": 79900, "settlement_review": 149900,
}





def seed(apps, schema_editor):
    Feature = apps.get_model("admin_console", "Feature")
    for key, solution in FEATURE_SOLUTIONS.items():
        Feature.objects.filter(key=key, solution_name="").update(solution_name=solution)
        if key in STARTING_MONTHLY_PRICES:
            Feature.objects.filter(key=key, monthly_price__isnull=True).update(monthly_price=STARTING_MONTHLY_PRICES[key])
    for index, (key, name, solution) in enumerate(FLEET_FEATURES):
        feature, _ = Feature.objects.get_or_create(key=key, defaults={"name": name, "solution_name": solution,
            "monthly_price": STARTING_MONTHLY_PRICES[key], "sort_order": 100 + index,
            "description": "Independently configurable access and monthly catalog price."})


class Migration(migrations.Migration):
    dependencies = [("admin_console", "0009_feature_monthly_price_feature_price_basis_and_more")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
