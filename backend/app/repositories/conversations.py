from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Conversation


class ConversationRepository:
    @staticmethod
    def create(session: Session, user_id: UUID, title: str) -> Conversation:
        conversation = Conversation(user_id=user_id, title=title)
        session.add(conversation)
        session.flush()
        return conversation

    @staticmethod
    def get_for_user(
        session: Session,
        conversation_id: UUID,
        user_id: UUID,
    ) -> Conversation | None:
        statement = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
        return session.scalar(statement)

    @staticmethod
    def list_for_user(session: Session, user_id: UUID) -> list[Conversation]:
        statement = (
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.created_at.desc(), Conversation.id)
        )
        return list(session.scalars(statement))
