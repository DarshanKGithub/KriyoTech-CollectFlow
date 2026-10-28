from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("matching", "0002_matchingsetting")]

    operations = [migrations.AddField(
        model_name="matchingsetting",
        name="over_receipt_tolerance_percent",
        field=models.DecimalField(decimal_places=3, default=0, max_digits=7),
    )]
