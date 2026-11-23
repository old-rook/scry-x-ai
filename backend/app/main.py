from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.v1.auth import admin_router, router as auth_router
from app.api.v1.answers import router as answers_router
from app.api.v1.cards import router as cards_router
from app.api.v1.health import router as health_router
from app.core.config import Settings
from app.db.database import Database
from app.providers.base import CardProvider
from app.providers.errors import CardProviderError
from app.providers.scryfall import ScryfallProvider
from app.rules.service import RulesService
from app.services.ai_generation import AIGenerationService, build_ai_generation_service
from app.services.card_extraction import CardCatalog


def create_app(
    settings: Settings | None = None,
    card_provider: CardProvider | None = None,
    rules_service: RulesService | None = None,
    ai_generation_service: AIGenerationService | None = None,
) -> FastAPI:
    settings = settings or Settings()
    database = Database(settings.database_url)
    card_provider = card_provider if card_provider is not None else ScryfallProvider()
    rules_service = rules_service or RulesService(settings.rules_storage_dir)
    ai_generation_service = ai_generation_service or build_ai_generation_service(settings, database)
    card_catalog = CardCatalog(settings.card_catalog_path, card_provider)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await rules_service.start_background_refresh(
            settings.rules_refresh_mode,
            settings.rules_refresh_interval_hours,
        )
        card_catalog.start_background_refresh()
        try:
            yield
        finally:
            try:
                await card_catalog.close()
            finally:
                try:
                    await rules_service.close()
                finally:
                    try:
                        await card_provider.close()
                    finally:
                        try:
                            await ai_generation_service.close()
                        finally:
                            database.dispose()

    app = FastAPI(
        title=settings.app_name,
        description="Unofficial Magic: The Gathering rules research assistant",
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, _exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": "Invalid request"})

    @app.exception_handler(CardProviderError)
    async def card_provider_error(_request: Request, exc: CardProviderError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": {"code": exc.code, "message": exc.message}},
        )

    app.state.database = database
    app.state.settings = settings
    app.state.card_provider = card_provider
    app.state.card_catalog = card_catalog
    app.state.rules_service = rules_service
    app.state.ai_generation_service = ai_generation_service
    app.include_router(health_router, prefix=settings.api_v1_prefix)
    app.include_router(cards_router, prefix=settings.api_v1_prefix)
    app.include_router(answers_router, prefix=settings.api_v1_prefix)
    app.include_router(auth_router, prefix=settings.api_v1_prefix)
    app.include_router(admin_router, prefix=settings.api_v1_prefix)

    @app.get("/api/debug/routes", include_in_schema=False)
    async def debug_routes():
        return {
            "docs_url": app.docs_url,
            "openapi_url": app.openapi_url,
            "routes": [
                getattr(route, "path", None)
                for route in app.routes
            ],
        }

    return app


app = create_app()
