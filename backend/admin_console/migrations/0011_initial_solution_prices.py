from django.db import migrations


PRICES = {
    "invoice_upload": 99900, "ai_extraction": 149900, "email_invoice_intake": 49900,
    "po_grn_matching": 149900, "duplicate_detection": 49900, "approval_workflow": 99900,
    "multi_level_approval": 49900, "auto_approval": 49900, "payment_tracking": 149900,
    "credit_debit_notes": 49900, "custom_fields": 29900, "bulk_actions": 49900,
    "tally_csv_export": 29900, "tally_xml_integration": 99900, "api_access": 99900,
    "advanced_reports": 99900, "whatsapp_intake": 49900, "sso": 149900, "priority_support": 99900,
}


def seed(apps, schema_editor):
    Feature = apps.get_model("admin_console", "Feature")
    for key, price in PRICES.items():
        Feature.objects.filter(key=key, monthly_price__isnull=True).update(monthly_price=price)


class Migration(migrations.Migration):
    dependencies = [("admin_console", "0010_solution_feature_catalog")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
