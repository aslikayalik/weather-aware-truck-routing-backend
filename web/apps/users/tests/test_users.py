import pytest
from django.urls import reverse

from apps.user_roles.models import UserRole
from apps.users.models import Profile, User

pytestmark = pytest.mark.django_db


def test_create_user_requires_email():
    with pytest.raises(ValueError):
        User.objects.create_user(email="", password="x")


def test_create_superuser_flags():
    admin = User.objects.create_superuser(email="admin@example.com", password="Passw0rd!x")
    assert admin.is_staff and admin.is_superuser
    assert admin.check_password("Passw0rd!x")


def test_me_requires_auth(api_client_unauthorized):
    response = api_client_unauthorized.get("/api/v1/user/me/")
    assert response.status_code == 401


def test_me_returns_current_user(api_client_user, user1):
    Profile.objects.create(user=user1)
    response = api_client_user.get("/api/v1/user/me/")
    assert response.status_code == 200
    assert response.json()["email"] == user1.email


def test_user_cannot_assign_higher_role(api_client_user, user1):
    low = UserRole.objects.create(name="operator", display_name="Operator", rank=10)
    high = UserRole.objects.create(name="admin", display_name="Admin", rank=100)
    user1.role = low
    user1.save()

    payload = {
        "first_name": "A",
        "last_name": "B",
        "email": "new@example.com",
        "password": "Passw0rd!x",
        "password_confirmation": "Passw0rd!x",
        "role": str(high.id),
        "profile": {},
    }
    response = api_client_user.post("/api/v1/user/admin/", payload, format="json")
    assert response.status_code == 403


def test_health_check(client):
    response = client.get(reverse("health_check"))
    assert response.status_code == 200
