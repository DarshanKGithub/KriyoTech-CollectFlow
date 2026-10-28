from django.core.management.base import BaseCommand
from invoices.extraction import recover_stalled_extractions


class Command(BaseCommand):
    help = "Release stale invoice extraction jobs for retry, even when Celery is offline."

    def handle(self, *args, **options):
        count = recover_stalled_extractions()
        self.stdout.write(self.style.SUCCESS(f"Released {count} stalled extraction jobs for retry."))
