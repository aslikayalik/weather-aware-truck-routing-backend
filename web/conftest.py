import pytest
from rest_framework.test import APIClient

from apps.users.models import User


@pytest.fixture
def user1() -> User:
    return User.objects.create_user(email="user1@example.com", password="Passw0rd!x")


@pytest.fixture
def api_client_unauthorized() -> APIClient:
    return APIClient()


@pytest.fixture
def api_client_user(user1) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user1)
    return client
