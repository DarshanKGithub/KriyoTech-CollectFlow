from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("communications", "0003_whatsappconsent"),
    ]

    operations = [
        migrations.AddField(
            model_name="whatsappmessagedraft",
            name="send_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
