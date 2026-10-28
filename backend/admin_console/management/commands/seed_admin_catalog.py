from django.core.management.base import BaseCommand
from admin_console.models import Feature, Plan, PlanFeature


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
        features = {key: Feature.objects.get_or_create(key=key, defaults={"name": name})[0] for key, name in FEATURES}
        plans = [
            ("Trial", 0, 0, 0, 20, 2, 14), ("Starter", 750000, None, 7500000, 100, 3, 0),
            ("Growth", 1500000, None, 15000000, 400, 10, 0), ("Control", 3000000, None, 30000000, 1200, None, 0),
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
        self.stdout.write(self.style.SUCCESS("Plan and feature catalog seeded."))
