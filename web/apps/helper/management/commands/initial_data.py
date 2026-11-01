import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.users.models import Profile
from apps.user_roles.models import UserRole
from apps.user_group.models import UserGroup

User = get_user_model()

ADMIN_USER_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@example.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")
ADMIN_ROLE_NAME = "admin"
ADMIN_ROLE_DISPLAY_NAME = "Administrator"
ADMIN_ROLE_RANK = 100


class Command(BaseCommand):
    help = "Create initial data for the application."

    def handle(self, *args, **options):
        admin_role, created = UserRole.objects.get_or_create(
            name=ADMIN_ROLE_NAME,
            defaults={"display_name": ADMIN_ROLE_DISPLAY_NAME, "rank": ADMIN_ROLE_RANK},
        )
        if created:
            self.stdout.write(f"Created role: {ADMIN_ROLE_NAME}")

        if not User.objects.exists():
            self.stdout.write("Creating Super User")
            admin = User.objects.create_superuser(
                password=ADMIN_PASSWORD,
                email=ADMIN_USER_EMAIL,
                role=admin_role,
                first_name="Super",
                last_name="Admin",
            )
            Profile.objects.create(user=admin, initials="SA")
            self.stdout.write(f"Created superuser: {ADMIN_USER_EMAIL}")

        if not UserGroup.objects.exists():
            self.stdout.write("Creating default user group")
            UserGroup.objects.create(
                name=UserGroup.EVERYONE, description="Default Group for Everyone"
            )
