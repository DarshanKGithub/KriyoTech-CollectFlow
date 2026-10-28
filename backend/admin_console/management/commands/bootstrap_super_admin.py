import secrets
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from admin_console.models import AdminAuditLog, AdminStaff


class Command(BaseCommand):
    help = "Create the first internal Super Admin with a one-time generated password."

    def add_arguments(self, parser):
        parser.add_argument("email", help="Email address for the initial Super Admin")

    @transaction.atomic
    def handle(self, *args, **options):
        email = options["email"].strip().lower()
        if AdminStaff.objects.filter(role=AdminStaff.Role.SUPER_ADMIN, is_active=True).exists():
            raise CommandError("An active Super Admin already exists; refusing to create another bootstrap account.")
        User = get_user_model()
        if User.objects.filter(email__iexact=email).exists():
            raise CommandError("That email already belongs to an account. Use provision_admin_staff only after verifying its owner.")
        password = secrets.token_urlsafe(32)
        user = User.objects.create_user(username=email, email=email, password=password)
        staff = AdminStaff.objects.create(user=user, role=AdminStaff.Role.SUPER_ADMIN)
        AdminAuditLog.objects.create(actor=user, actor_role=staff.role, action="INITIAL_SUPER_ADMIN_BOOTSTRAPPED", object_type="AdminStaff", object_id=str(staff.pk), metadata={"email": email})
        self.stdout.write(self.style.SUCCESS("Initial Super Admin created."))
        self.stdout.write(f"Email: {email}")
        self.stdout.write(f"One-time password (copy it now): {password}")
        self.stdout.write(self.style.WARNING("Store this password in a password manager and rotate it after first sign-in. This command will not show it again."))
