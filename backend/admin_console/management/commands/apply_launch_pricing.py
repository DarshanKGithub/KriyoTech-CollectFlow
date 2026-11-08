from django.core.management.base import BaseCommand
from django.db import transaction
from admin_console.launch_pricing import PLAN_PRICES, REASON, REVIEW_DATE
from admin_console.models import AdminAuditLog, Feature, Plan
from admin_console.solution_catalog import STARTING_MONTHLY_PRICES


class Command(BaseCommand):
    help = "Preview or apply the reviewed India SME launch rates; leaves usage, access and payment records intact."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Save catalog and standard-plan prices with before/after audit records.")

    @transaction.atomic
    def handle(self, *args, **options):
        applied = options["apply"]
        changed = 0
        for feature in Feature.objects.select_for_update().filter(key__in=STARTING_MONTHLY_PRICES).order_by("key"):
            after = {"monthly_price": STARTING_MONTHLY_PRICES[feature.key], "price_basis": "COMPANY"}
            before = {key: getattr(feature, key) for key in after}
            if before == after:
                continue
            changed += 1
            self.stdout.write(f"Feature {feature.key}: {before['monthly_price']} -> {after['monthly_price']} paise/month")
            if applied:
                for key, value in after.items():
                    setattr(feature, key, value)
                feature.save(update_fields=list(after))
                AdminAuditLog.objects.create(action="FEATURE_PRICING_REVIEW_APPLIED", object_type="Feature",
                    object_id=str(feature.pk), reason=REASON, metadata={"review_date": REVIEW_DATE,
                        "feature_key": feature.key, "before": before, "after": after})
        fields = ("monthly_price", "quarterly_price", "annual_price")
        for plan in Plan.objects.select_for_update().filter(slug__in=PLAN_PRICES, currency="INR").order_by("slug"):
            before = {field: getattr(plan, field) for field in fields}
            after = dict(zip(fields, PLAN_PRICES[plan.slug]))
            if before == after:
                continue
            changed += 1
            self.stdout.write(f"Plan {plan.slug}: {before} -> {after} paise")
            if applied:
                for field, value in after.items():
                    setattr(plan, field, value)
                plan.save(update_fields=[*fields, "updated_at"])
                AdminAuditLog.objects.create(action="PLAN_PRICING_REVIEW_APPLIED", object_type="Plan",
                    object_id=str(plan.pk), reason=REASON, metadata={"review_date": REVIEW_DATE,
                        "plan_slug": plan.slug, "before": before, "after": after})
        self.stdout.write(self.style.SUCCESS(f"{'Applied' if applied else 'Previewed'} {changed} changes. Enterprise and custom-plan prices are retained."))
