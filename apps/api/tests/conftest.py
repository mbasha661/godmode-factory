import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.auth import AuthUser, get_current_user
from app.config import get_settings


@pytest.fixture()
def settings():
    s = get_settings()
    s.supabase_url = ""
    s.supabase_anon_key = ""
    s.supabase_service_role_key = ""
    s.gemini_api_key = ""
    s.groq_api_key = ""
    return s


@pytest.fixture()
def user_a(settings):
    return AuthUser(id="11111111-1111-1111-1111-111111111111", email="a@example.com")


@pytest.fixture()
def user_b(settings):
    return AuthUser(id="22222222-2222-2222-2222-222222222222", email="b@example.com")


def make_client(user: AuthUser) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings] = lambda: get_settings()
    return TestClient(app)


@pytest.fixture()
def client_a(user_a):
    return make_client(user_a)


@pytest.fixture()
def client_b(user_b):
    return make_client(user_b)
