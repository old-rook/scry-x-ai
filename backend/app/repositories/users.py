from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import User


class UserRepository:
    @staticmethod
    def create(session: Session, user_id: UUID | None = None) -> User:
        user = User(id=user_id) if user_id is not None else User()
        session.add(user)
        session.flush()
        return user

    @staticmethod
    def get(session: Session, user_id: UUID) -> User | None:
        return session.get(User, user_id)

    @staticmethod
    def get_by_email(session: Session, email: str) -> User | None:
        return session.scalar(select(User).where(User.email == email.lower().strip()))

    @staticmethod
    def create_authenticated(
        session: Session,
        email: str,
        password_hash: str,
        role: str = "user",
    ) -> User:
        user = User(email=email.lower().strip(), password_hash=password_hash, role=role)
        session.add(user)
        session.flush()
        return user

