from typing import Literal

from app.schemas.base import StrictBaseModel


class DependencyStatus(StrictBaseModel):
    status: Literal[
        "ok",
        "degraded",
        "unavailable",
        "not_configured",
        "stale",
    ]


class HealthResponse(StrictBaseModel):
    status: Literal["ok", "degraded", "unavailable"]
    database: DependencyStatus
    scryfall: DependencyStatus
    rules: DependencyStatus
    ai: DependencyStatus
