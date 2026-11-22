from fastapi import APIRouter, Depends

from app.schemas.health import DependencyStatus, HealthResponse
from app.db.database import Database, get_database


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(database: Database = Depends(get_database)) -> HealthResponse:
    database_status = database.health_status()
    return HealthResponse(
        status="degraded" if database_status == "unavailable" else "ok",
        database=DependencyStatus(status=database_status),
        scryfall=DependencyStatus(status="not_configured"),
        rules=DependencyStatus(status="not_configured"),
        ai=DependencyStatus(status="not_configured"),
    )
