import logging
from collections.abc import Generator
from contextlib import contextmanager

from fastapi import HTTPException, Request, status
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.pool import StaticPool
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from pydantic import SecretStr


logger = logging.getLogger(__name__)


class Database:
    def __init__(self, database_url: SecretStr | str | None) -> None:
        if isinstance(database_url, SecretStr):
            database_url = database_url.get_secret_value()
        if database_url and database_url.startswith("sqlite"):
            if ":memory:" in database_url:
                self.engine: Engine | None = create_engine(
                    database_url,
                    poolclass=StaticPool,
                    connect_args={"check_same_thread": False},
                )
            else:
                self.engine = create_engine(
                    database_url,
                    pool_pre_ping=True,
                    connect_args={"check_same_thread": False},
                )
        else:
            self.engine = create_engine(database_url, pool_pre_ping=True) if database_url else None
        self._session_factory = (
            sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
            if self.engine is not None
            else None
        )

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        if self._session_factory is None:
            raise RuntimeError("Database is not configured")
        with self._session_factory() as session:
            yield session

    def health_status(self) -> str:
        if self.engine is None:
            return "not_configured"
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError as error:
            logger.warning(
                "Database health check failed (%s)",
                type(error).__name__,
            )
            return "unavailable"
        return "ok"

    def dispose(self) -> None:
        if self.engine is not None:
            self.engine.dispose()


def get_database(request: Request) -> Database:
    return request.app.state.database


def get_session(request: Request) -> Generator[Session, None, None]:
    database: Database = request.app.state.database
    if database.engine is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not configured",
        )
    with database.session() as session:
        yield session
