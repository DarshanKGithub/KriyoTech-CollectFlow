from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("invoices", "0007_invoice_financial_locked_at")]
    operations = [migrations.AddField(model_name="invoice", name="automation", field=models.JSONField(default=dict, blank=True, editable=False))]
