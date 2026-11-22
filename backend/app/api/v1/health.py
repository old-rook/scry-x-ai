from fastapi import APIRouter

from app.schemas.health import DependencyStatus, HealthResponse


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        database=DependencyStatus(status="not_configured"),
        scryfall=DependencyStatus(status="not_configured"),
        rules=DependencyStatus(status="not_configured"),
        ai=DependencyStatus(status="not_configured"),
    )
