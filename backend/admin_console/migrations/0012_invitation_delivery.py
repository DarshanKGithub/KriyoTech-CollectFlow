import django.utils.timezone
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_alter_invitation_role_alter_membership_role"),
        ("admin_console", "0011_initial_solution_prices"),
    ]

    operations = [
        migrations.CreateModel(
            name="InvitationDelivery",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("PENDING", "Pending"), ("PROCESSING", "Processing"), ("SUBMITTED", "Submitted to email provider"), ("CONSOLE_ONLY", "Console only"), ("FAILED", "Failed"), ("CANCELLED", "Cancelled")], db_index=True, default="PENDING", max_length=12)),
                ("encrypted_token", models.TextField(blank=True)),
                ("attempt_count", models.PositiveSmallIntegerField(default=0)),
                ("next_attempt_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("processing_token", models.UUIDField(blank=True, null=True)),
                ("error_message", models.CharField(blank=True, max_length=300)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("invitation", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="delivery", to="accounts.invitation")),
            ],
        ),
        migrations.AddIndex(
            model_name="invitationdelivery",
            index=models.Index(fields=["status", "next_attempt_at"], name="admin_conso_status_ba8d04_idx"),
        ),
    ]
