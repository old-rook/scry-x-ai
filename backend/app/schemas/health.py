from datetime import date, datetime
from typing import Literal

from pydantic import Field

from app.schemas.base import StrictBaseModel


class DependencyStatus(StrictBaseModel):
    status: Literal[
        "ok",
        "degraded",
        "unavailable",
        "not_configured",
        "stale",
    ]


class AIProviderStatus(StrictBaseModel):
    provider: str
    model: str
    availability: Literal["configured", "unavailable", "disabled"]


class AIStatus(DependencyStatus):
    providers: list[AIProviderStatus] = Field(default_factory=list)


class RulesVersionSummary(StrictBaseModel):
    version: str
    publication_date: date | None = None
    discovered_at: datetime | None = None
    verified_at: datetime | None = None


class RulesStatus(DependencyStatus):
    latest_known_official: RulesVersionSummary | None = None
    latest_verified_local: RulesVersionSummary | None = None
    refresh_in_progress: bool = False


class HealthResponse(StrictBaseModel):
    status: Literal["ok", "degraded", "unavailable"]
    database: DependencyStatus
    scryfall: DependencyStatus
    rules: RulesStatus
    ai: AIStatus
