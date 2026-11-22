import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from typing import Literal

from app.core.config import Settings
from app.db.database import Database
from app.providers.ai import (
    AIAuditPersistenceError,
    AIBudgetExceededError,
    AIConfigurationError,
    AIErrorClass,
    AIInvalidRequestError,
    AIMessage,
    AIPaidUsageDisabledError,
    AIProvider,
    AIProviderError,
    AIRequest,
    AIResult,
)
from app.repositories.paid_budget import BudgetReservation, PaidBudgetRepository
from app.repositories.provider_audit import ProviderAuditRepository


logger = logging.getLogger(__name__)
_BUDGET_PRECISION = Decimal("0.000000000001")
_MAX_STORABLE_COST_USD = Decimal("99999999.999999999999")


@dataclass(frozen=True)
class ModelRoute:
    provider: str
    model: str
    cost: Literal["free", "paid"]
    adapter: AIProvider


class AIGenerationService:
    def __init__(
        self,
        settings: Settings,
        database: Database,
        routes: list[ModelRoute] | None = None,
    ) -> None:
        self.settings = settings
        self.database = database
        self.routes = routes or []

    def health_summary(self) -> list[dict[str, str]]:
        return [
            {
                "provider": route.provider,
                "model": route.model,
                "availability": (
                    "disabled"
                    if route.cost == "paid" and not self.settings.llm_paid_enabled
                    else route.adapter.health()
                ),
            }
            for route in self.routes
        ]

    async def close(self) -> None:
        for route in self.routes:
            await route.adapter.close()

    async def generate(self, request: AIRequest) -> AIResult:
        if not self.routes:
            raise AIConfigurationError()
        self._ensure_audit_database()
        if not request.messages or any(
            message.role not in {"system", "user", "assistant"} or not message.content.strip()
            for message in request.messages
        ):
            raise AIInvalidRequestError()

        reservation: BudgetReservation | None = None
        reservation_unknown = False
        for route_index, route in enumerate(self.routes):
            if route.cost == "paid":
                if not self.settings.llm_paid_enabled:
                    error = AIPaidUsageDisabledError()
                    await self._record(
                        route,
                        outcome="failure",
                        cost_tier=route.cost,
                        error_classification=error.classification.value,
                    )
                    raise error
                if reservation_unknown:
                    error = AIBudgetExceededError()
                    await self._record(
                        route,
                        outcome="failure",
                        cost_tier=route.cost,
                        error_classification=error.classification.value,
                    )
                    raise error
                if reservation is None:
                    reservation = await self._reserve_paid_budget(route)

            route_error: AIProviderError | None = None
            for attempt in range(self.settings.llm_max_retries + 1):
                try:
                    result = await route.adapter.generate(request)
                except AIProviderError as error:
                    await self._record(
                        route,
                        outcome="failure",
                        cost_tier=route.cost,
                        error_classification=error.classification.value,
                    )
                    route_error = error
                    if route.cost == "paid":
                        await self._mark_unknown_budget(reservation)
                        reservation_unknown = True
                        break
                    if not error.failover_eligible or attempt >= self.settings.llm_max_retries:
                        break
                    delay = min(
                        self.settings.llm_retry_base_delay_seconds * (2**attempt),
                        self.settings.llm_retry_max_delay_seconds,
                    )
                    if delay:
                        await asyncio.sleep(delay)
                except Exception:
                    # Unexpected adapter failures are classified without exposing details.
                    error = AIProviderError()
                    await self._record(
                        route,
                        outcome="failure",
                        cost_tier=route.cost,
                        error_classification=AIErrorClass.UNKNOWN.value,
                    )
                    route_error = error
                    if route.cost == "paid":
                        await self._mark_unknown_budget(reservation)
                        reservation_unknown = True
                    break
                else:
                    reported_cost = self._trusted_reported_cost(result)
                    usage = getattr(result, "usage", None)
                    await self._record(
                        route,
                        outcome="success",
                        cost_tier=route.cost,
                        input_tokens=self._trusted_token_count(
                            getattr(usage, "input_tokens", None)
                        ),
                        output_tokens=self._trusted_token_count(
                            getattr(usage, "output_tokens", None)
                        ),
                        reported_cost_usd=reported_cost,
                    )
                    if route.cost == "paid":
                        if reported_cost is None:
                            await self._mark_unknown_budget(reservation)
                            reservation_unknown = True
                        else:
                            await self._settle_paid_budget(
                                reservation,
                                self._round_budget_amount_up(reported_cost),
                            )
                    return result

            if route_error is None:
                raise AIProviderError()
            if (
                not route_error.failover_eligible
                or route_index == len(self.routes) - 1
            ):
                raise route_error
        raise AIProviderError()

    def _ensure_audit_database(self) -> None:
        if self.database.engine is None or self.database.health_status() != "ok":
            raise AIAuditPersistenceError() from None

    @staticmethod
    def _trusted_reported_cost(result: AIResult) -> Decimal | None:
        usage = getattr(result, "usage", None)
        cost = getattr(usage, "reported_cost_usd", None)
        if (
            not isinstance(cost, Decimal)
            or not cost.is_finite()
            or cost < 0
            or cost > _MAX_STORABLE_COST_USD
        ):
            return None
        return cost

    @staticmethod
    def _round_budget_amount_up(value: Decimal) -> Decimal:
        try:
            return value.quantize(_BUDGET_PRECISION, rounding=ROUND_CEILING)
        except InvalidOperation:
            return _MAX_STORABLE_COST_USD

    @staticmethod
    def _trusted_token_count(value: object) -> int | None:
        if type(value) is int and value >= 0:
            return value
        return None

    async def _reserve_paid_budget(self, route: ModelRoute) -> BudgetReservation:
        now = datetime.now(timezone.utc)
        month_start = date(now.year, now.month, 1)
        try:
            with self.database.session() as session:
                reservation = PaidBudgetRepository.reserve(
                    session,
                    month_start=month_start,
                    cap_usd=self._round_budget_amount_up(self.settings.llm_monthly_cap_usd),
                    minimum_remaining_usd=self._round_budget_amount_up(
                        self.settings.llm_paid_minimum_remaining_usd
                    ),
                )
        except Exception:
            raise AIAuditPersistenceError() from None
        if reservation is None:
            error = AIBudgetExceededError()
            await self._record(
                route,
                outcome="failure",
                cost_tier=route.cost,
                error_classification=error.classification.value,
            )
            raise error
        return reservation

    async def _mark_unknown_budget(self, reservation: BudgetReservation | None) -> None:
        if reservation is None:
            raise AIAuditPersistenceError() from None
        try:
            with self.database.session() as session:
                PaidBudgetRepository.mark_unknown(session, reservation)
        except Exception:
            # The committed remaining-budget reservation remains held if this update fails.
            logger.warning("AI paid-budget unknown-cost settlement failed; reservation remains held")

    async def _settle_paid_budget(
        self,
        reservation: BudgetReservation | None,
        reported_cost: Decimal,
    ) -> None:
        if reservation is None:
            raise AIAuditPersistenceError() from None
        try:
            with self.database.session() as session:
                PaidBudgetRepository.settle(
                    session,
                    reservation,
                    actual_cost_usd=reported_cost,
                )
        except Exception:
            # A committed reservation remains fail-closed if exact settlement fails.
            logger.warning("AI paid-budget settlement failed; reservation remains held")

    async def _record(
        self,
        route: ModelRoute,
        *,
        outcome: str,
        cost_tier: str = "free",
        error_classification: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        reported_cost_usd: Decimal | None = None,
    ) -> None:
        if self.database.engine is None:
            raise AIAuditPersistenceError() from None
        try:
            with self.database.session() as session:
                ProviderAuditRepository.record(
                    session,
                    provider=route.provider,
                    model=route.model,
                    outcome=outcome,
                    cost_tier=cost_tier,
                    error_classification=error_classification,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    reported_cost_usd=reported_cost_usd,
                )
                session.commit()
        except Exception:
            raise AIAuditPersistenceError() from None


def build_ai_generation_service(settings: Settings, database: Database) -> AIGenerationService:
    from app.providers.gemini import GeminiProvider
    from app.providers.openrouter import OpenRouterProvider

    routes: list[ModelRoute] = []
    configured = (
        (
            settings.llm_primary_provider,
            settings.llm_primary_model,
            settings.llm_primary_model_cost,
        ),
        (
            settings.llm_fallback_provider,
            settings.llm_fallback_model,
            settings.llm_fallback_model_cost,
        ),
    )
    for provider_name, model, cost in configured:
        if provider_name is None or model is None or cost is None:
            continue
        api_key = (
            settings.llm_openrouter_api_key
            if provider_name == "openrouter"
            else settings.llm_gemini_api_key
        )
        adapter_type = OpenRouterProvider if provider_name == "openrouter" else GeminiProvider
        adapter = adapter_type(
            model,
            api_key,
            timeout=settings.llm_request_timeout_seconds,
        )
        routes.append(ModelRoute(provider_name, model, cost, adapter))
    return AIGenerationService(settings, database, routes)
