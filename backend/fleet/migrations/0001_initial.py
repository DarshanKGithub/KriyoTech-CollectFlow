import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("documents", "0001_initial"),
        ("tenants", "0005_tenant_soft_delete"),
    ]

    operations = [
        migrations.CreateModel(
            name="FleetDriver",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=160)),
                ("contact_phone", models.CharField(blank=True, max_length=32)),
                ("reference_code", models.CharField(blank=True, max_length=64)),
                ("status", models.CharField(choices=[("ACTIVE", "Active"), ("INACTIVE", "Inactive")], default="ACTIVE", max_length=12)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="fleet_drivers", to="tenants.tenant")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="fleet_driver_profiles", to=settings.AUTH_USER_MODEL)),
            ],
            options={"indexes": [models.Index(fields=["tenant", "status", "name"], name="fleet_driver_tenant__c6fd80_idx")]},
        ),
        migrations.CreateModel(
            name="FleetVehicle",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("registration_number", models.CharField(max_length=24)),
                ("normalized_registration", models.CharField(max_length=24)),
                ("make_model", models.CharField(blank=True, max_length=120)),
                ("capacity", models.DecimalField(blank=True, decimal_places=3, max_digits=12, null=True)),
                ("ownership_type", models.CharField(blank=True, max_length=20)),
                ("status", models.CharField(choices=[("ACTIVE", "Active"), ("INACTIVE", "Inactive")], default="ACTIVE", max_length=12)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="fleet_vehicles", to="tenants.tenant")),
            ],
            options={"indexes": [models.Index(fields=["tenant", "status", "registration_number"], name="fleet_veh_tenant__b3df69_idx")]},
        ),
        migrations.CreateModel(
            name="FleetTrip",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("trip_number", models.CharField(max_length=64)),
                ("customer_reference", models.CharField(blank=True, max_length=160)),
                ("origin", models.CharField(blank=True, max_length=160)),
                ("destination", models.CharField(blank=True, max_length=160)),
                ("starts_at", models.DateTimeField(blank=True, null=True)),
                ("ends_at", models.DateTimeField(blank=True, null=True)),
                ("odometer_start", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("odometer_end", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("status", models.CharField(choices=[("DRAFT", "Draft"), ("IN_PROGRESS", "In progress"), ("SUBMITTED", "Submitted"), ("APPROVED", "Approved"), ("REJECTED", "Rejected")], default="DRAFT", max_length=16)),
                ("submitted_at", models.DateTimeField(blank=True, null=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("review_note", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="fleet_trips_created", to=settings.AUTH_USER_MODEL)),
                ("driver", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="trips", to="fleet.fleetdriver")),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="fleet_trips_reviewed", to=settings.AUTH_USER_MODEL)),
                ("submitted_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="fleet_trips_submitted", to=settings.AUTH_USER_MODEL)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="fleet_trips", to="tenants.tenant")),
                ("vehicle", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="trips", to="fleet.fleetvehicle")),
            ],
            options={"indexes": [models.Index(fields=["tenant", "status", "starts_at"], name="fleet_trip_tenant__68e400_idx"), models.Index(fields=["tenant", "vehicle", "starts_at"], name="fleet_trip_tenant__b5d4e6_idx"), models.Index(fields=["tenant", "driver", "starts_at"], name="fleet_trip_tenant__f24f7e_idx")]},
        ),
        migrations.CreateModel(
            name="TripRevenueLine",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("description", models.CharField(max_length=160)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=18)),
                ("is_estimated", models.BooleanField(default=False)),
                ("status", models.CharField(choices=[("DRAFT", "Draft"), ("SUBMITTED", "Submitted"), ("APPROVED", "Approved")], default="DRAFT", max_length=12)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="fleet_trip_revenue", to="tenants.tenant")),
                ("trip", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="revenue_lines", to="fleet.fleettrip")),
            ],
        ),
        migrations.CreateModel(
            name="TripExpenseLine",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("category", models.CharField(choices=[("FUEL", "Fuel"), ("TOLL", "Toll / FASTag"), ("LOADING", "Loading / unloading"), ("ALLOWANCE", "Food / allowance"), ("PERMIT", "Permit"), ("REPAIR", "Repair / maintenance"), ("PARKING", "Parking"), ("COMMISSION", "Commission"), ("OTHER", "Other")], default="OTHER", max_length=20)),
                ("description", models.CharField(max_length=200)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=18)),
                ("budgeted_amount", models.DecimalField(blank=True, decimal_places=2, max_digits=18, null=True)),
                ("incurred_at", models.DateField(blank=True, null=True)),
                ("payee", models.CharField(blank=True, max_length=160)),
                ("payment_reference", models.CharField(blank=True, max_length=120)),
                ("is_estimated", models.BooleanField(default=False)),
                ("status", models.CharField(choices=[("DRAFT", "Draft"), ("SUBMITTED", "Submitted"), ("APPROVED", "Approved"), ("REJECTED", "Rejected")], default="DRAFT", max_length=12)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ("receipt", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="fleet_expenses", to="documents.document")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="fleet_trip_expenses", to="tenants.tenant")),
                ("trip", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="expense_lines", to="fleet.fleettrip")),
            ],
            options={"indexes": [models.Index(fields=["tenant", "status", "category"], name="fleet_ex_tenant__bd6906_idx"), models.Index(fields=["tenant", "trip", "incurred_at"], name="fleet_ex_tenant__b0b15b_idx")]},
        ),
        migrations.CreateModel(
            name="FleetFollowUp",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("category", models.CharField(max_length=40)),
                ("description", models.CharField(max_length=240)),
                ("due_at", models.DateTimeField(blank=True, null=True)),
                ("status", models.CharField(choices=[("OPEN", "Open"), ("IN_PROGRESS", "In progress"), ("RESOLVED", "Resolved"), ("WAIVED", "Waived")], default="OPEN", max_length=16)),
                ("resolution_note", models.TextField(blank=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="fleet_followups_created", to=settings.AUTH_USER_MODEL)),
                ("resolved_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="fleet_followups_resolved", to=settings.AUTH_USER_MODEL)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="fleet_follow_ups", to="tenants.tenant")),
                ("trip", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="follow_ups", to="fleet.fleettrip")),
            ],
            options={"indexes": [models.Index(fields=["tenant", "status", "due_at"], name="fleet_foll_tenant__c611e0_idx")]},
        ),
        migrations.AddConstraint(model_name="fleetdriver", constraint=models.UniqueConstraint(condition=~models.Q(reference_code=""), fields=("tenant", "reference_code"), name="uniq_fleet_driver_reference")),
        migrations.AddConstraint(model_name="fleetvehicle", constraint=models.UniqueConstraint(fields=("tenant", "normalized_registration"), name="uniq_fleet_vehicle_registration")),
        migrations.AddConstraint(model_name="fleettrip", constraint=models.UniqueConstraint(fields=("tenant", "trip_number"), name="uniq_fleet_trip_number")),
    ]
