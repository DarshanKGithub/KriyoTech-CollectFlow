from django.core.management.base import BaseCommand, CommandError
from phase3.services import deliver_due_webhooks


class Command(BaseCommand):
    help = "Deliver due KriyoPay webhook events and schedule bounded retries."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        limit = options["limit"]
        if not 1 <= limit <= 1000:
            raise CommandError("--limit must be from 1 to 1000")
        count = deliver_due_webhooks(limit=limit)
        self.stdout.write(self.style.SUCCESS(f"Processed {count} webhook delivery attempt(s)."))
