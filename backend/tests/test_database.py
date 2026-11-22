from pathlib import Path
from uuid import uuid4

import pytest
import httpx
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.schemas.auth import AuthResponse, LoginRequest, LogoutResponse, RegisterRequest
from app.db.base import Base
from app.db.database import Database
from app.db.models import Conversation, Message, User
from app.main import create_app
from app.repositories.conversations import ConversationRepository
from app.repositories.messages import MessageRepository
from app.repositories.users import UserRepository
from app.rules.service import RulesService


def offline_rules_service(path: Path) -> RulesService:
    return RulesService(
        path,
        transport=httpx.MockTransport(lambda request: httpx.Response(503, request=request)),
    )


@pytest.fixture
def database():
    database = Database("sqlite+pysqlite:///:memory:")
    assert database.engine is not None
    Base.metadata.create_all(database.engine)
    yield database
    database.dispose()


def test_database_health_status_without_configuration() -> None:
    assert Database(None).health_status() == "not_configured"


def test_database_health_status_with_sqlite() -> None:
    database = Database("sqlite+pysqlite:///:memory:")
    try:
        assert database.health_status() == "ok"
    finally:
        database.dispose()


def test_database_health_status_reports_connection_failure(monkeypatch) -> None:
    database = Database("sqlite+pysqlite:///:memory:")
    assert database.engine is not None

    def fail_connection():
        raise SQLAlchemyError("connection failed")

    monkeypatch.setattr(database.engine, "connect", fail_connection)
    try:
        assert database.health_status() == "unavailable"
    finally:
        database.dispose()


def test_health_endpoint_reports_database_failure_without_details(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Database, "health_status", lambda self: "unavailable")

    with TestClient(
        create_app(Settings(rules_refresh_mode="external"), rules_service=offline_rules_service(tmp_path))
    ) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["database"] == {"status": "unavailable"}
    assert "password" not in response.text.lower()


def test_health_endpoint_reports_configured_database(tmp_path: Path) -> None:
    settings = Settings(database_url="sqlite+pysqlite:///:memory:")

    with TestClient(
        create_app(settings, rules_service=offline_rules_service(tmp_path))
    ) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["database"] == {"status": "ok"}


def test_repositories_create_and_retrieve_user_conversation_and_messages(database) -> None:
    with database.session() as session:
        user = UserRepository.create(session)
        conversation = ConversationRepository.create(
            session,
            user_id=user.id,
            title="Rules question",
        )
        user_message = MessageRepository.create(
            session,
            conversation_id=conversation.id,
            user_id=user.id,
            role="user",
            content="How does this interaction work?",
        )
        assistant_message = MessageRepository.create(
            session,
            conversation_id=conversation.id,
            user_id=user.id,
            role="assistant",
            content="It depends on the relevant rule.",
        )
        session.commit()

        assert UserRepository.get(session, user.id) is not None
        assert (
            ConversationRepository.get_for_user(
                session,
                conversation.id,
                user.id,
            )
            is not None
        )
        assert ConversationRepository.get_for_user(
            session,
            conversation.id,
            uuid4(),
        ) is None
        assert ConversationRepository.list_for_user(session, user.id) == [conversation]
        assert MessageRepository.list_for_conversation(
            session,
            conversation.id,
            user.id,
        ) == [user_message, assistant_message]
        assert MessageRepository.list_for_conversation(
            session,
            conversation.id,
            uuid4(),
        ) == []


def test_message_repository_rejects_non_owner(database) -> None:
    with database.session() as session:
        user = UserRepository.create(session)
        conversation = ConversationRepository.create(
            session,
            user_id=user.id,
            title="Private conversation",
        )
        session.commit()

        with pytest.raises(LookupError, match="Conversation not found"):
            MessageRepository.create(
                session,
                conversation_id=conversation.id,
                user_id=uuid4(),
                role="user",
                content="Unauthorized message",
            )

        assert MessageRepository.list_for_conversation(
            session,
            conversation.id,
            user.id,
        ) == []


def test_database_session_closes_without_implicit_commit(database) -> None:
    with database.session() as session:
        UserRepository.create(session)

    with database.session() as session:
        assert session.scalar(select(User)) is None


def test_database_session_rolls_back_after_exception(database) -> None:
    with pytest.raises(RuntimeError, match="operation failed"):
        with database.session() as session:
            UserRepository.create(session)
            raise RuntimeError("operation failed")

    with database.session() as session:
        assert session.scalar(select(User)) is None


def test_initial_migration_upgrades_and_downgrades_sqlite() -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    migration_config = Config(str(backend_dir / "alembic.ini"))
    engine = create_engine("sqlite+pysqlite:///:memory:")

    try:
        with engine.connect() as connection:
            migration_config.attributes["connection"] = connection
            command.upgrade(migration_config, "head")
            assert set(inspect(connection).get_table_names()) == {
                "alembic_version",
                "users",
                "conversations",
                "messages",
                "provider_audit",
                "ai_paid_monthly_budgets",
                "ai_paid_budget_reservations",
            }
            assert compare_metadata(
                MigrationContext.configure(connection),
                Base.metadata,
            ) == []

            command.downgrade(migration_config, "base")
            assert inspect(connection).get_table_names() == ["alembic_version"]
            assert connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).all() == []
    finally:
        engine.dispose()


def test_persistence_relationships_do_not_cascade_deletes() -> None:
    assert User.conversations.property.cascade.delete is False
    assert User.conversations.property.cascade.delete_orphan is False
    assert Conversation.messages.property.cascade.delete is False
    assert Conversation.messages.property.cascade.delete_orphan is False
    for table in (Conversation.__table__, Message.__table__):
        assert all(foreign_key.ondelete is None for foreign_key in table.foreign_keys)
