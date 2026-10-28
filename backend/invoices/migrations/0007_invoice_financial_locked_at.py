from django.db import migrations, models
from django.db.models import Q
from django.utils import timezone


def backfill_lock(apps, schema_editor):
    Invoice = apps.get_model("invoices", "Invoice")
    ids = Invoice.objects.using(schema_editor.connection.alias).filter(
        Q(status__in=["APPROVED", "PAYMENT_READY", "EXPORTED"])
        | ~Q(payment_status="UNPAID") | Q(payment_allocations__isnull=False)
    ).values("pk")
    Invoice.objects.using(schema_editor.connection.alias).filter(pk__in=ids).update(financial_locked_at=timezone.now())


class Migration(migrations.Migration):
    dependencies = [("invoices", "0006_extraction_recovery"), ("payments", "0001_initial")]
    operations = [
        migrations.AddField(model_name="invoice", name="financial_locked_at", field=models.DateTimeField(blank=True, editable=False, null=True)),
        migrations.RunPython(backfill_lock, migrations.RunPython.noop),
    ]
