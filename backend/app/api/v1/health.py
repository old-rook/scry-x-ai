from fastapi import APIRouter, Depends

from app.api.v1.cards import get_card_provider
from app.providers.base import CardProvider
from app.schemas.health import DependencyStatus, HealthResponse
from app.db.database import Database, get_database


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(
    database: Database = Depends(get_database),
    card_provider: CardProvider = Depends(get_card_provider),
) -> HealthResponse:
    database_status = database.health_status()
    try:
        scryfall_status = "ok" if await card_provider.health_check() else "unavailable"
    except Exception:
        scryfall_status = "unavailable"
    return HealthResponse(
        status=(
            "degraded"
            if database_status == "unavailable" or scryfall_status == "unavailable"
            else "ok"
        ),
        database=DependencyStatus(status=database_status),
        scryfall=DependencyStatus(status=scryfall_status),
        rules=DependencyStatus(status="not_configured"),
        ai=DependencyStatus(status="not_configured"),
    )
