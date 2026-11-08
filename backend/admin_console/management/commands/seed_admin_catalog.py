from django.core.management.base import BaseCommand
from django.core.management import call_command
from admin_console.models import Feature, Plan, PlanFeature
from admin_console.solution_catalog import FEATURE_SOLUTIONS, FLEET_FEATURES, STARTING_MONTHLY_PRICES
from admin_console.launch_pricing import PLAN_PRICES


FEATURES = [
    ("invoice_upload", "Invoice upload"), ("ai_extraction", "AI invoice extraction"),
    ("email_invoice_intake", "Email invoice inbox"), ("po_grn_matching", "PO and GRN matching"),
    ("duplicate_detection", "Duplicate detection"), ("approval_workflow", "Approval workflow"),
    ("multi_level_approval", "Multi-level approvals"), ("auto_approval", "Auto-approval rules"),
    ("payment_tracking", "Payment tracking"), ("credit_debit_notes", "Credit/debit notes"),
    ("custom_fields", "Custom fields"), ("bulk_actions", "Bulk actions"),
    ("tally_csv_export", "Tally CSV export"), ("tally_xml_integration", "Direct Tally integration"),
    ("api_access", "Public API access"), ("advanced_reports", "Advanced reports"),
    ("fleet_management", "Fleet & Trips"),
    ("whatsapp_intake", "WhatsApp invoice intake"), ("sso", "Single sign-on"),
    ("priority_support", "Priority support"),
]


class Command(BaseCommand):
    help = "Create the initial configurable KriyoPay plans and feature catalog."

    def handle(self, *args, **options):
        features = {key: Feature.objects.get_or_create(key=key, defaults={"name": name,
            "solution_name": FEATURE_SOLUTIONS.get(key, ""), "monthly_price": STARTING_MONTHLY_PRICES.get(key)})[0] for key, name in FEATURES}
        for index, (key, name, solution) in enumerate(FLEET_FEATURES):
            Feature.objects.get_or_create(key=key, defaults={"name": name, "solution_name": solution,
                "monthly_price": STARTING_MONTHLY_PRICES.get(key), "sort_order": 100 + index})
        plans = [
            ("Trial", *PLAN_PRICES["trial"], 20, 2, 14), ("Starter", *PLAN_PRICES["starter"], 100, 3, 0),
            ("Growth", *PLAN_PRICES["growth"], 400, 10, 0), ("Control", *PLAN_PRICES["control"], 1200, None, 0),
            ("Enterprise", None, None, None, None, None, 0),
        ]
        for index, (name, monthly, quarterly, annual, invoice_limit, user_limit, trial_days) in enumerate(plans):
            plan, _ = Plan.objects.update_or_create(slug=name.lower(), defaults={
                "name": name, "monthly_price": monthly, "quarterly_price": quarterly,
                "annual_price": annual, "invoice_limit": invoice_limit, "user_limit": user_limit,
                "trial_days": trial_days, "sort_order": index,
                "description": "Unlimited read-only users" if name == "Control" else "Custom commercial terms" if name == "Enterprise" else "",
            })
            for key, feature in features.items():
                enabled = key == "invoice_upload" or (name == "Trial" and key in {"ai_extraction", "po_grn_matching"}) or (name == "Starter" and key in {"ai_extraction", "po_grn_matching", "duplicate_detection", "approval_workflow", "payment_tracking", "tally_csv_export"}) or (name == "Growth" and key not in {"tally_xml_integration", "api_access", "advanced_reports", "whatsapp_intake", "sso", "priority_support"}) or (name == "Control" and key not in {"whatsapp_intake", "sso"}) or name == "Enterprise"
                PlanFeature.objects.update_or_create(plan=plan, feature=feature, defaults={"enabled": enabled})
        call_command("seed_solution_plans", stdout=self.stdout)
        self.stdout.write(self.style.SUCCESS("Plan and feature catalog seeded."))
