from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from admin_console.models import AdminStaff
from admin_console.models import AdminAuditLog


class Command(BaseCommand):
    help = "Grant an existing account a KriyoPay internal staff role."
    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument("role", choices=[choice for choice, _ in AdminStaff.Role.choices])
    def handle(self, *args, **options):
        user = get_user_model().objects.filter(email__iexact=options["email"]).first()
        if not user:
            raise CommandError("Create the account first, then provision the internal role.")
        staff, created = AdminStaff.objects.update_or_create(user=user, defaults={"role": options["role"], "is_active": True})
        AdminAuditLog.objects.create(actor=user, actor_role=staff.role, action="ADMIN_STAFF_PROVISIONED", object_type="AdminStaff", object_id=str(staff.pk), metadata={"role": staff.role, "created": created})
        self.stdout.write(self.style.SUCCESS(f"{'Provisioned' if created else 'Updated'} {staff.user.email} as {staff.role}."))
