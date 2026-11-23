from datetime import datetime
from typing import Literal

from pydantic import Field, HttpUrl, StrictInt, field_validator

from app.schemas.base import StrictBaseModel


class CardRuling(StrictBaseModel):
    oracle_card_id: str = Field(min_length=1)
    card_name: str = Field(min_length=1)
    published_at: datetime
    comment: str = Field(min_length=1)
    source: Literal["scryfall", "gatherer"]
    source_url: HttpUrl | None = None


class CardDetail(StrictBaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    scryfall_uri: HttpUrl | None = None
    mana_cost: str | None = None
    type_line: str | None = None
    oracle_text: str | None = None
    set_name: str | None = None
    rarity: str | None = None
    image_urls: dict[str, HttpUrl] = Field(default_factory=dict)
    rulings: list[CardRuling] = Field(default_factory=list)
    source: Literal["scryfall"] = "scryfall"
    source_updated_at: datetime | None = None


class CardSearchRequest(StrictBaseModel):
    q: str = Field(min_length=1, max_length=403)
    limit: StrictInt = Field(default=10, ge=1, le=100)

    @field_validator("q")
    @classmethod
    def validate_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("q must not be blank")
        return value.strip()


class CardSearchResponse(StrictBaseModel):
    cards: list[CardDetail] = Field(default_factory=list)
    total: int = Field(default=0, ge=0)
