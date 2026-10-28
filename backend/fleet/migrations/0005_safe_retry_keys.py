from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("fleet", "0004_fleetreminderdelivery")]

    operations = [
        migrations.AddField(
            model_name="tripexpenseline",
            name="idempotency_key",
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="driversalarypayment",
            name="idempotency_key",
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="tripexpenseline",
            constraint=models.UniqueConstraint(condition=models.Q(idempotency_key__isnull=False), fields=("tenant", "idempotency_key"), name="uniq_fleet_expense_idempotency"),
        ),
        migrations.AddConstraint(
            model_name="driversalarypayment",
            constraint=models.UniqueConstraint(condition=models.Q(idempotency_key__isnull=False), fields=("tenant", "idempotency_key"), name="uniq_fleet_salary_payment_idempotency"),
        ),
    ]
