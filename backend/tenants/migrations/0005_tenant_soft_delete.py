from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("tenants", "0004_branch")]

    operations = [
        migrations.AddField(model_name="tenant", name="is_deleted", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="tenant", name="deleted_at", field=models.DateTimeField(blank=True, null=True)),
    ]
