import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("exports_app", "0001_initial"),
        ("tenants", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [migrations.CreateModel(
        name="TallyLedgerMapping",
        fields=[
            ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ("dimension", models.CharField(choices=[("VENDOR_LEDGER", "Vendor ledger"), ("PURCHASE_LEDGER", "Purchase ledger"), ("GST_LEDGER", "GST ledger"), ("TDS_LEDGER", "TDS ledger"), ("COST_CENTER", "Cost center"), ("VOUCHER_TYPE", "Voucher type")], max_length=24)),
            ("source_key", models.CharField(max_length=120)),
            ("ledger_name", models.CharField(max_length=120)),
            ("active", models.BooleanField(default=True)),
            ("updated_at", models.DateTimeField(auto_now=True)),
            ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_tally_mappings", to=settings.AUTH_USER_MODEL)),
            ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tally_ledger_mappings", to="tenants.tenant")),
        ],
        options={"indexes": [models.Index(fields=["tenant", "dimension", "active"], name="exports_app_tenant__22e3a2_idx")], "constraints": [models.UniqueConstraint(fields=("tenant", "dimension", "source_key"), name="uniq_tally_mapping_source")]},
    )]
