from fastapi import APIRouter, Depends, Request

from app.api.v1.cards import get_card_provider
from app.providers.base import CardProvider
from app.schemas.health import DependencyStatus, HealthResponse
from app.db.database import Database, get_database
from app.services.ai_generation import AIGenerationService


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(
    request: Request,
    database: Database = Depends(get_database),
    card_provider: CardProvider = Depends(get_card_provider),
) -> HealthResponse:
    database_status = database.health_status()
    try:
        scryfall_status = "ok" if await card_provider.health_check() else "unavailable"
    except Exception:
        scryfall_status = "unavailable"
    ai_service: AIGenerationService = request.app.state.ai_generation_service
    ai_providers = ai_service.health_summary()
    ai_status = (
        "not_configured"
        if not ai_providers
        else "ok"
        if any(provider["availability"] == "configured" for provider in ai_providers)
        else "unavailable"
    )
    return HealthResponse(
        status=(
            "degraded"
            if database_status == "unavailable"
            or scryfall_status == "unavailable"
            or ai_status == "unavailable"
            else "ok"
        ),
        database=DependencyStatus(status=database_status),
        scryfall=DependencyStatus(status=scryfall_status),
        rules=DependencyStatus(status="not_configured"),
        ai={"status": ai_status, "providers": ai_providers},
    )
