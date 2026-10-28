from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("payments", "0001_initial")]

    operations = [
        migrations.AddField(model_name="payment", name="idempotency_key", field=models.UUIDField(blank=True, null=True)),
        migrations.AddConstraint(model_name="payment", constraint=models.UniqueConstraint(condition=models.Q(idempotency_key__isnull=False), fields=("tenant", "idempotency_key"), name="uniq_payment_idempotency")),
    ]
