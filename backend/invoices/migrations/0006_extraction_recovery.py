from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):
    dependencies = [("invoices", "0005_invoice_source_channel")]
    operations = [
        migrations.AddField(model_name="extractionresult", name="updated_at", field=models.DateTimeField(auto_now=True, db_index=True, default=timezone.now), preserve_default=False),
        migrations.AddField(model_name="extractionresult", name="attempts", field=models.PositiveSmallIntegerField(default=0)),
        migrations.AddField(model_name="extractionresult", name="claim_token", field=models.UUIDField(blank=True, null=True)),
    ]
