import getpass
from django.contrib.auth import get_user_model, password_validation
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError
from admin_console.models import AdminAuditLog, AdminStaff


class Command(BaseCommand):
    help = "Create a local KriyoPay internal staff account with a separate admin role."

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument("role", choices=[choice for choice, _ in AdminStaff.Role.choices])

    def handle(self, *args, **options):
        email = options["email"].strip().lower()
        User = get_user_model()
        if User.objects.filter(email__iexact=email).exists():
            raise CommandError("That email already has an account. Use provision_admin_staff to add its internal role.")
        password = getpass.getpass("Password: ")
        confirmation = getpass.getpass("Confirm password: ")
        if not password or password != confirmation:
            raise CommandError("Passwords are empty or do not match.")
        try:
            password_validation.validate_password(password)
        except ValidationError as error:
            raise CommandError(" ".join(error.messages)) from error
        user = User.objects.create_user(username=email, email=email, password=password)
        staff = AdminStaff.objects.create(user=user, role=options["role"])
        AdminAuditLog.objects.create(actor=user, actor_role=staff.role, action="ADMIN_STAFF_CREATED", object_type="AdminStaff", object_id=str(staff.pk), metadata={"role": staff.role})
        self.stdout.write(self.style.SUCCESS(f"Created internal staff account {user.email} with role {staff.role}."))
