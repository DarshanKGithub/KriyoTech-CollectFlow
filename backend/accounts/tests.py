import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from accounts.models import User


@pytest.mark.django_db
def test_refresh_extends_session_and_rotates_refresh_token():
    user = User.objects.create_user(username="session@kriyopay.test", email="session@kriyopay.test", password="correct-horse-battery")
    original_refresh = str(RefreshToken.for_user(user))
    client = APIClient()

    refreshed = client.post("/api/v1/auth/refresh", {"refresh": original_refresh}, format="json")
    assert refreshed.status_code == 200, refreshed.data
    assert "access" in refreshed.data and "refresh" in refreshed.data
    assert refreshed.data["refresh"] != original_refresh

    access = AccessToken(refreshed.data["access"])
    rotated_refresh = RefreshToken(refreshed.data["refresh"])
    assert access["exp"] - access["iat"] == 30 * 60
    assert rotated_refresh["exp"] - rotated_refresh["iat"] == 14 * 24 * 60 * 60

    reused = client.post("/api/v1/auth/refresh", {"refresh": original_refresh}, format="json")
    assert reused.status_code == 401
