from django.db import migrations


def add_fleet_feature(apps, schema_editor):
    Feature = apps.get_model("admin_console", "Feature")
    Plan = apps.get_model("admin_console", "Plan")
    PlanFeature = apps.get_model("admin_console", "PlanFeature")

    feature, _ = Feature.objects.update_or_create(
        key="fleet_management",
        defaults={
            "name": "Fleet & Trips",
            "description": "Truck, driver, trip, delivery proof, follow-up, and driver finance workflows.",
            "is_active": True,
            "sort_order": 100,
        },
    )
    for plan in Plan.objects.all():
        enabled = plan.slug in {"growth", "control", "enterprise"}
        PlanFeature.objects.update_or_create(
            plan=plan,
            feature=feature,
            defaults={"enabled": enabled, "limit_value": None, "limit_period": ""},
        )


def remove_fleet_feature(apps, schema_editor):
    Feature = apps.get_model("admin_console", "Feature")
    Feature.objects.filter(key="fleet_management").delete()


class Migration(migrations.Migration):
    dependencies = [("admin_console", "0003_payment_offline_reference_alter_payment_status_and_more")]

    operations = [migrations.RunPython(add_fleet_feature, remove_fleet_feature)]
