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


class HealthResponse(StrictBaseModel):
    status: Literal["ok", "degraded", "unavailable"]
    database: DependencyStatus
    scryfall: DependencyStatus
    rules: DependencyStatus
    ai: AIStatus
