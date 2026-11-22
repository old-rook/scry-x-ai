from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Conversation, Message


class MessageRepository:
    @staticmethod
    def create(
        session: Session,
        conversation_id: UUID,
        user_id: UUID,
        role: Literal["user", "assistant"],
        content: str,
    ) -> Message:
        owned_conversation = session.scalar(
            select(Conversation.id).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        )
        if owned_conversation is None:
            raise LookupError("Conversation not found")

        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
        )
        session.add(message)
        session.flush()
        return message

    @staticmethod
    def list_for_conversation(
        session: Session,
        conversation_id: UUID,
        user_id: UUID,
    ) -> list[Message]:
        statement = (
            select(Message)
            .join(Conversation)
            .where(
                Message.conversation_id == conversation_id,
                Conversation.user_id == user_id,
            )
            .order_by(Message.created_at, Message.id)
        )
        return list(session.scalars(statement))
