from django.db import migrations, models


ROLE_CHOICES = [
    ("OWNER", "Owner"),
    ("FINANCE", "Finance"),
    ("PURCHASE", "Purchase"),
    ("STORE", "Store"),
    ("APPROVER", "Approver"),
    ("AUDITOR", "Auditor"),
    ("DRIVER", "Driver"),
]


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_membership_branch_scope_enabled_branchmembership")]

    operations = [
        migrations.AlterField(
            model_name="membership",
            name="role",
            field=models.CharField(max_length=20, choices=ROLE_CHOICES),
        ),
        migrations.AlterField(
            model_name="invitation",
            name="role",
            field=models.CharField(max_length=20, choices=ROLE_CHOICES),
        ),
    ]
