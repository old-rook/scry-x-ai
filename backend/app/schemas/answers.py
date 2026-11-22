from datetime import datetime
from typing import Literal

from pydantic import Field, HttpUrl, StrictBool, field_validator, model_validator

from app.schemas.base import StrictBaseModel


class AnswerSource(StrictBaseModel):
    id: str = Field(min_length=1)
    source_type: Literal["comprehensive_rules", "card_ruling", "oracle_text"]
    source_reference: str = Field(min_length=1)
    source_url: HttpUrl | None = None
    evidence_text: str = Field(min_length=1, max_length=2_000)
    retrieved_at: datetime


class ComprehensiveRuleSource(StrictBaseModel):
    section: str = Field(min_length=1)
    title: str | None = None
    text: str = Field(min_length=1)
    source_url: HttpUrl
    checksum: str = Field(min_length=64, max_length=64)
    ruleset_version: str = Field(min_length=1)


class ConversationTurn(StrictBaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=1200)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("conversation turn must not be blank")
        return value.strip()


class AnswerRequest(StrictBaseModel):
    conversation_id: str | None = Field(default=None, max_length=100)
    question: str = Field(min_length=1, max_length=5000)
    card_names: list[str] = Field(default_factory=list, max_length=20)
    guest: StrictBool = True
    conversation_context: list[ConversationTurn] = Field(default_factory=list, max_length=6)

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be blank")
        return value.strip()

    @model_validator(mode="after")
    def validate_context_budget(self) -> "AnswerRequest":
        if sum(len(turn.content) for turn in self.conversation_context) > 3600:
            raise ValueError("conversation context exceeds the allowed size")
        if any(not name.strip() or len(name) > 100 for name in self.card_names):
            raise ValueError("card names must be non-empty and at most 100 characters")
        return self


class AnswerResponse(StrictBaseModel):
    answer_id: str = Field(min_length=1)
    conversation_id: str | None = None
    verdict: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    comprehensive_rules: list[ComprehensiveRuleSource] = Field(default_factory=list)
    card_rulings: list[AnswerSource] = Field(default_factory=list)
    additional_considerations: list[str] = Field(default_factory=list)
    model: str = Field(min_length=1)
    evidence_status: Literal["complete", "partial", "insufficient"]
    disclaimer: str = Field(min_length=1)
