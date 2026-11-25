from io import StringIO

import pytest
from django.core.management import call_command

from agrisec.users.models import User


@pytest.mark.django_db
class TestUserManager:
    def test_create_user(self):
        user = User.objects.create_user(
            email="john@example.com",
            password="something-r@nd0m!",  # noqa: S106
        )
        assert user.email == "john@example.com"
        assert not user.is_staff
        assert not user.is_superuser
        assert user.check_password("something-r@nd0m!")
        assert user.username == "john"

    def test_create_superuser(self):
        user = User.objects.create_superuser(
            email="admin@example.com",
            password="something-r@nd0m!",  # noqa: S106
        )
        assert user.email == "admin@example.com"
        assert user.is_staff
        assert user.is_superuser
        assert user.username == "admin"

    def test_create_multiple_users_with_same_email_prefix_generates_unique_usernames(self):
        u1 = User.objects.create_superuser(
            email="admin@example.com",
            password="something-r@nd0m!",  # noqa: S106
        )
        u2 = User.objects.create_superuser(
            email="admin@agrisec.com",
            password="something-r@nd0m!",  # noqa: S106
        )
        assert u1.username == "admin"
        assert u2.username.startswith("admin_")
        assert u1.username != u2.username


@pytest.mark.django_db
def test_createsuperuser_command_multiple_times():
    """Ensure createsuperuser command works repeatedly without username collisions."""
    for email in ("henry@example.com", "sarah@example.com"):
        out = StringIO()
        command_result = call_command(
            "createsuperuser",
            "--email",
            email,
            interactive=False,
            stdout=out,
        )
        assert command_result is None
        assert out.getvalue() == "Superuser created successfully.\n"

    assert User.objects.filter(is_superuser=True).count() == 2
