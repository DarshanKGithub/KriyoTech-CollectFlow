from django.core.management.base import BaseCommand, CommandError
from phase3.services import count_due_webhooks, deliver_due_webhooks


class Command(BaseCommand):
    help = "Deliver due KriyoPay webhook events and schedule bounded retries."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--dry-run", action="store_true", help="Count due deliveries without contacting recipients.")

    def handle(self, *args, **options):
        limit = options["limit"]
        if not 1 <= limit <= 1000:
            raise CommandError("--limit must be from 1 to 1000")
        if options["dry_run"]:
            count = count_due_webhooks(limit=limit)
            self.stdout.write(f"Dry run: {count} webhook delivery attempt(s) are due.")
            return
        count = deliver_due_webhooks(limit=limit)
        self.stdout.write(self.style.SUCCESS(f"Processed {count} webhook delivery attempt(s)."))
