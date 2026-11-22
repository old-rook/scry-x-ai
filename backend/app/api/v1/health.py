from fastapi import APIRouter, Depends, Request

from app.api.v1.cards import get_card_provider
from app.providers.base import CardProvider
from app.providers.errors import CardProviderError
from app.schemas.health import DependencyStatus, HealthResponse
from app.db.database import Database, get_database
from app.services.ai_generation import AIGenerationService
from app.rules.service import RulesService


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
    except CardProviderError:
        scryfall_status = "unavailable"

    rules_service: RulesService = request.app.state.rules_service
    rules_status = rules_service.health_summary()

    ai_service: AIGenerationService = request.app.state.ai_generation_service
    ai_providers = ai_service.health_summary()
    availabilities = {provider["availability"] for provider in ai_providers}
    if not availabilities or availabilities == {"disabled"}:
        ai_status = "not_configured"
    elif "configured" in availabilities:
        ai_status = "degraded" if "unavailable" in availabilities else "ok"
    else:
        ai_status = "unavailable"

    component_statuses = {
        database_status,
        scryfall_status,
        rules_status["status"],
        ai_status,
    }
    return HealthResponse(
        status="degraded"
        if component_statuses.intersection({"degraded", "unavailable", "stale"})
        else "ok",
        database=DependencyStatus(status=database_status),
        scryfall=DependencyStatus(status=scryfall_status),
        rules=rules_status,
        ai={"status": ai_status, "providers": ai_providers},
    )
