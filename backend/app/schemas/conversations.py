from datetime import datetime

from pydantic import Field, field_validator

from app.schemas.base import StrictBaseModel


class ConversationCreateRequest(StrictBaseModel):
    title: str = Field(min_length=1, max_length=200)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("title must not be blank")
        return value.strip()


class ConversationDetail(StrictBaseModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(StrictBaseModel):
    conversations: list[ConversationDetail] = Field(default_factory=list)
    total: int = Field(default=0, ge=0)
