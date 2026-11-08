from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from admin_console.launch_pricing import PLAN_PRICES, SOLUTION_PLANS
from admin_console.models import AdminAuditLog, Feature, Plan, PlanFeature


class Command(BaseCommand):
    help = "Create the four priced solution packages without changing existing subscriptions or plan configuration."

    @transaction.atomic
    def handle(self, *args, **options):
        catalog = list(Feature.objects.filter(is_active=True))
        keys = {feature.key for feature in catalog}
        missing = set().union(*(row["features"] for row in SOLUTION_PLANS.values())) - keys
        if missing:
            raise CommandError("Seed the feature catalog first; missing: " + ", ".join(sorted(missing)))
        for index, (slug, spec) in enumerate(SOLUTION_PLANS.items()):
            monthly, quarterly, annual = PLAN_PRICES[slug]
            plan, created = Plan.objects.get_or_create(slug=slug, defaults={
                "name": spec["name"], "description": spec["description"], "currency": "INR",
                "monthly_price": monthly, "quarterly_price": quarterly, "annual_price": annual,
                "is_active": True, "is_public": True, "sort_order": 10 + index,
                "invoice_limit": 0, "ai_extraction_limit": 0, "user_limit": 5,
                "trial_days": 0,
            })
            if not created:
                self.stdout.write(f"Retained existing {plan.name} configuration.")
                continue
            PlanFeature.objects.bulk_create([PlanFeature(plan=plan, feature=feature,
                enabled=feature.key in spec["features"]) for feature in catalog])
            AdminAuditLog.objects.create(action="SOLUTION_PLAN_CREATED", object_type="Plan", object_id=str(plan.pk),
                reason="Add reviewed per-company solution packages requested by product owner.", metadata={
                    "plan_slug": slug, "monthly_price": monthly, "quarterly_price": quarterly,
                    "annual_price": annual, "enabled_features": sorted(spec["features"]),
                })
            self.stdout.write(self.style.SUCCESS(f"Created {plan.name}: INR {monthly / 100:.2f}/company/month."))
