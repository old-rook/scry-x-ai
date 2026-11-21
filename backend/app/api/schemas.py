from typing import Literal
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class RulesVersion(BaseModel):
    version_id: str
    source_version_date: str | None = None
    fetched_at: str | None = None
    source_url: str


class CardResponse(BaseModel):
    scryfall_id: str
    oracle_id: str
    name: str
    type_line: str | None = None
    mana_cost: str | None = None
    oracle_text: str | None = None
    image_uri: str | None = None


class AmbiguousCard(BaseModel):
    mentioned_name: str
    candidates: list[CardResponse]


class IdentifyRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


class IdentifyResponse(BaseModel):
    status: Literal["resolved", "needs_selection"]
    cards: list[CardResponse] = []
    ambiguous: list[AmbiguousCard] = []


class ConfirmedCard(BaseModel):
    scryfall_id: str


class JudgeRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    confirmed_cards: list[ConfirmedCard] = []


class Citation(BaseModel):
    evidence_id: str
    kind: Literal["comprehensive_rule", "card_text", "card_ruling"]
    reason: str = ""
    label: str = ""
    text: str = ""
    source_url: str | None = None


class ModelAnswer(BaseModel):
    status: Literal["answered", "needs_clarification", "insufficient_evidence"]
    summary: str
    explanation: list[str] = []
    assumptions: list[str] = []
    citations: list[Citation] = []
    uncertainties: list[str] = []
    clarifying_question: str | None = None


class JudgeResponse(BaseModel):
    status: Literal["answered", "needs_clarification", "insufficient_evidence", "needs_selection"]
    summary: str
    explanation: list[str] = []
    cards: list[CardResponse] = []
    ambiguous: list[AmbiguousCard] = []
    citations: list[Citation] = []
    rules_version: RulesVersion
    assumptions: list[str] = []
    uncertainties: list[str] = []
    clarifying_question: str | None = None
