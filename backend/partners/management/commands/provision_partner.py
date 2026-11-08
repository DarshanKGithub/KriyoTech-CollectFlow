from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Retired reseller command. This application now operates as KriyoPay only."

    def handle(self, *args, **options):
        raise CommandError("Reseller operations are retired. Existing schema data has been preserved.")
