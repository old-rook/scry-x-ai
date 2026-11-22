from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel


router = APIRouter(tags=["health"])


class DependencyStatus(BaseModel):
    status: Literal["not_configured"]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    database: DependencyStatus
    scryfall: DependencyStatus
    rules: DependencyStatus
    ai: DependencyStatus


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        database=DependencyStatus(status="not_configured"),
        scryfall=DependencyStatus(status="not_configured"),
        rules=DependencyStatus(status="not_configured"),
        ai=DependencyStatus(status="not_configured"),
    )
