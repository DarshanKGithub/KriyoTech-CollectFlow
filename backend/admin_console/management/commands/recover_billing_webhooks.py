from django.core.management.base import BaseCommand
from admin_console.webhook_recovery import recover_events


class Command(BaseCommand):
    help = "Publish due billing events from durable storage without making provider calls."
    def handle(self, *args, **options):
        self.stdout.write(f"Published {recover_events()} due event(s). Exhausted events require investigation.")
