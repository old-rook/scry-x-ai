from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.base import Base
from app.db.models import User
from app.main import create_app
from app.repositories.conversations import ConversationRepository


@pytest.fixture
def auth_client():
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        jwt_signing_key="test-signing-key-not-for-production",
    )
    app = create_app(settings)
    assert app.state.database.engine is not None
    Base.metadata.create_all(app.state.database.engine)
    with TestClient(app) as client:
        yield client, settings


def register(client: TestClient, email: str, password: str = "password123"):
    return client.post("/api/v1/auth/register", json={"email": email, "password": password})


def test_missing_malformed_expired_and_valid_credentials(auth_client) -> None:
    client, settings = auth_client

    missing = client.post("/api/v1/auth/logout")
    assert missing.status_code == 401

    malformed = client.post("/api/v1/auth/logout", headers={"Authorization": "Bearer not-a-jwt"})
    assert malformed.status_code == 401

    expired = jwt.encode(
        {
            "sub": str(uuid4()),
            "role": "user",
            "iat": datetime.now(timezone.utc) - timedelta(minutes=20),
            "exp": datetime.now(timezone.utc) - timedelta(minutes=5),
            "type": "access",
        },
        settings.jwt_signing_key.get_secret_value(),
        algorithm="HS256",
    )
    expired_response = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {expired}"})
    assert expired_response.status_code == 401

    registered = register(client, "valid@example.test")
    assert registered.status_code == 201
    token = registered.json()["access_token"]
    valid = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert valid.status_code == 200
    assert valid.json() == {"status": "logged_out"}
    assert "access_token" not in valid.text
    assert "password" not in valid.text.lower()


def test_login_and_duplicate_email(auth_client) -> None:
    client, _ = auth_client
    first = register(client, "Person@example.test", "secure-password")
    assert first.status_code == 201

    duplicate = register(client, "person@example.test", "another-password")
    assert duplicate.status_code == 409

    login = client.post("/api/v1/auth/login", json={"email": "person@example.test", "password": "secure-password"})
    assert login.status_code == 200
    assert login.json()["role"] == "user"

    bad_login = client.post("/api/v1/auth/login", json={"email": "person@example.test", "password": "wrong-password"})
    assert bad_login.status_code == 401


def test_cross_user_conversation_ownership(auth_client) -> None:
    client, _ = auth_client
    owner_response = register(client, "owner@example.test")
    other_response = register(client, "other@example.test")
    owner_id = owner_response.json()["user_id"]

    database = client.app.state.database
    with database.session() as session:
        conversation = ConversationRepository.create(session, UUID(owner_id), "Private")
        session.commit()
        assert ConversationRepository.require_owned(session, conversation.id, UUID(owner_id)) is not None
        with pytest.raises(LookupError, match="Conversation not found"):
            ConversationRepository.require_owned(session, conversation.id, UUID(other_response.json()["user_id"]))


def test_admin_authorization(auth_client) -> None:
    client, _ = auth_client
    user_response = register(client, "user@example.test")
    user_token = user_response.json()["access_token"]

    denied = client.get("/api/v1/admin/status", headers={"Authorization": f"Bearer {user_token}"})
    assert denied.status_code == 403

    database = client.app.state.database
    with database.session() as session:
        user = session.get(User, UUID(user_response.json()["user_id"]))
        user.role = "admin"
        session.commit()

    login = client.post("/api/v1/auth/login", json={"email": "user@example.test", "password": "password123"})
    admin_token = login.json()["access_token"]
    allowed = client.get("/api/v1/admin/status", headers={"Authorization": f"Bearer {admin_token}"})
    assert allowed.status_code == 200
    assert allowed.json() == {"status": "ok"}
