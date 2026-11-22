import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.db.base import Base
from app.db.database import Database
from app.db.models import AIPaidMonthlyBudget, AIPaidBudgetReservation, ProviderAudit
from app.main import create_app
from app.providers.scryfall import ScryfallProvider
from app.providers.ai import (
    AIAuditPersistenceError,
    AIBudgetExceededError,
    AIAuthenticationError,
    AIContextTooLargeError,
    AIConfigurationError,
    AIInvalidResponseError,
    AIInvalidRequestError,
    AIMessage,
    AIPaidUsageDisabledError,
    AIProviderUnavailableError,
    AIRequest,
    AIResult,
    AIRateLimitError,
    AIUsage,
    AITimeoutError,
)
from app.providers.gemini import GeminiProvider
from app.providers.openrouter import OpenRouterProvider
from app.repositories.provider_audit import ProviderAuditRepository
from app.repositories.paid_budget import PaidBudgetRepository
from app.rules.service import RulesService
from app.services.ai_generation import AIGenerationService, ModelRoute


def offline_rules_service(path: Path) -> RulesService:
    return RulesService(
        path,
        transport=httpx.MockTransport(lambda request: httpx.Response(503, request=request)),
    )


class FakeProvider:
    def __init__(self, provider: str, model: str, responses: list[object]) -> None:
        self.provider_name = provider
        self.model = model
        self.configured = True
        self.responses = responses
        self.requests: list[AIRequest] = []
        self.closed = False

    async def generate(self, request: AIRequest) -> AIResult:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    async def close(self) -> None:
        self.closed = True

    def health(self) -> str:
        return "configured" if self.configured else "unavailable"


def make_database() -> Database:
    database = Database("sqlite+pysqlite:///:memory:")
    assert database.engine is not None
    Base.metadata.create_all(database.engine)
    return database


def successful_result(provider: str, model: str, cost: Decimal | None = None) -> AIResult:
    return AIResult(provider, model, "safe answer", AIUsage(4, 3, cost))


def test_provider_http_adapters_extract_responses_and_usage() -> None:
    def openrouter_response(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-secret"
        body = __import__("json").loads(request.content)
        assert body["model"] == "configured/model"
        assert body["messages"] == [{"role": "user", "content": "question context"}]
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "answer"}}],
                "usage": {"prompt_tokens": 6, "completion_tokens": 2, "cost": "0.001"},
            },
        )

    async def execute() -> AIResult:
        provider = OpenRouterProvider(
            "configured/model",
            "test-secret",
            transport=httpx.MockTransport(openrouter_response),
        )
        try:
            return await provider.generate(AIRequest((AIMessage("user", "question context"),)))
        finally:
            await provider.close()

    result = asyncio.run(execute())
    assert result.text == "answer"
    assert result.usage.input_tokens == 6
    assert result.usage.output_tokens == 2
    assert result.usage.reported_cost_usd == Decimal("0.001")


def test_gemini_adapter_maps_neutral_context_and_usage() -> None:
    def response(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/models/configured-gemini:generateContent")
        assert request.headers["x-goog-api-key"] == "gemini-secret"
        import json

        payload = json.loads(request.content)
        assert payload["systemInstruction"]["parts"][0]["text"] == "grounding"
        assert payload["contents"] == [{"role": "user", "parts": [{"text": "question"}]}]
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": "answer"}]}}],
                "usageMetadata": {"promptTokenCount": 8, "candidatesTokenCount": 5},
            },
        )

    async def execute() -> AIResult:
        provider = GeminiProvider(
            "configured-gemini",
            "gemini-secret",
            transport=httpx.MockTransport(response),
        )
        try:
            return await provider.generate(
                AIRequest((AIMessage("system", "grounding"), AIMessage("user", "question")))
            )
        finally:
            await provider.close()

    result = asyncio.run(execute())
    assert result.text == "answer"
    assert result.usage.input_tokens == 8
    assert result.usage.output_tokens == 5
    assert result.usage.reported_cost_usd is None


@pytest.mark.parametrize(
    ("status_code", "error_type"),
    [(401, AIAuthenticationError), (429, AIRateLimitError), (413, AIContextTooLargeError)],
)
def test_http_errors_are_classified_without_returning_provider_body(
    status_code: int,
    error_type: type[Exception],
) -> None:
    async def execute() -> None:
        provider = OpenRouterProvider(
            "user/model",
            "secret",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    status_code,
                    json={"error": {"message": "secret provider body"}},
                )
            ),
        )
        try:
            with pytest.raises(error_type) as error:
                await provider.generate(AIRequest((AIMessage("user", "question"),)))
            assert "secret provider body" not in str(error.value)
            assert "secret" not in str(error.value)
        finally:
            await provider.close()

    asyncio.run(execute())


def test_malformed_provider_responses_are_classified_safely() -> None:
    async def execute() -> None:
        provider = GeminiProvider(
            "configured-model",
            "secret",
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"candidates": []})),
        )
        try:
            with pytest.raises(AIInvalidResponseError):
                await provider.generate(AIRequest((AIMessage("user", "question"),)))
        finally:
            await provider.close()

    asyncio.run(execute())


def test_http_timeout_is_classified_without_transport_details() -> None:
    async def execute() -> None:
        def timeout(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("private request URL", request=request)

        provider = OpenRouterProvider(
            "configured-model",
            "secret",
            transport=httpx.MockTransport(timeout),
        )
        try:
            with pytest.raises(AITimeoutError) as error:
                await provider.generate(AIRequest((AIMessage("user", "question"),)))
            assert "private request URL" not in str(error.value)
            assert "secret" not in str(error.value)
        finally:
            await provider.close()

    asyncio.run(execute())


def test_retry_bounds_fallback_order_and_preserved_context(monkeypatch) -> None:
    database = make_database()
    primary = FakeProvider(
        "openrouter",
        "primary/model",
        [AITimeoutError(), AITimeoutError()],
    )
    fallback = FakeProvider("gemini", "fallback/model", [successful_result("gemini", "fallback/model")])
    settings = Settings(
        llm_primary_provider="openrouter",
        llm_primary_model="primary/model",
        llm_primary_model_cost="free",
        llm_fallback_provider="gemini",
        llm_fallback_model="fallback/model",
        llm_fallback_model_cost="free",
        llm_max_retries=1,
        llm_retry_base_delay_seconds=0.1,
        llm_retry_max_delay_seconds=0.2,
    )
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr("app.services.ai_generation.asyncio.sleep", fake_sleep)
    service = AIGenerationService(
        settings,
        database,
        [
            ModelRoute("openrouter", "primary/model", "free", primary),
            ModelRoute("gemini", "fallback/model", "free", fallback),
        ],
    )
    request = AIRequest(
        (AIMessage("system", "retrieved rule context"), AIMessage("user", "question with context"))
    )
    try:
        result = asyncio.run(service.generate(request))
        assert result.provider == "gemini"
        assert delays == [0.1]
        assert len(primary.requests) == 2
        assert len(fallback.requests) == 1
        assert all(candidate is request for candidate in primary.requests + fallback.requests)
        with database.session() as session:
            rows = session.scalars(select(ProviderAudit).order_by(ProviderAudit.created_at)).all()
            assert [row.outcome for row in rows] == ["failure", "failure", "success"]
            assert rows[0].error_classification == "timeout"
            assert rows[-1].input_tokens == 4
    finally:
        database.dispose()


def test_authentication_failure_never_fails_over() -> None:
    database = make_database()
    primary = FakeProvider("openrouter", "primary", [AIAuthenticationError()])
    fallback = FakeProvider("gemini", "fallback", [successful_result("gemini", "fallback")])
    service = AIGenerationService(
        Settings(llm_primary_provider="openrouter", llm_primary_model="primary", llm_primary_model_cost="free"),
        database,
        [
            ModelRoute("openrouter", "primary", "free", primary),
            ModelRoute("gemini", "fallback", "free", fallback),
        ],
    )
    try:
        with pytest.raises(AIAuthenticationError):
            asyncio.run(service.generate(AIRequest((AIMessage("user", "question"),))))
        assert len(primary.requests) == 1
        assert fallback.requests == []
    finally:
        database.dispose()


@pytest.mark.parametrize(
    "failure",
    [AIConfigurationError(), AIInvalidRequestError(), AIContextTooLargeError()],
)
def test_non_availability_errors_never_fall_back(failure: Exception) -> None:
    database = make_database()
    primary = FakeProvider("openrouter", "primary", [failure])
    fallback = FakeProvider("gemini", "fallback", [successful_result("gemini", "fallback")])
    service = AIGenerationService(
        Settings(llm_primary_provider="openrouter", llm_primary_model="primary", llm_primary_model_cost="free"),
        database,
        [
            ModelRoute("openrouter", "primary", "free", primary),
            ModelRoute("gemini", "fallback", "free", fallback),
        ],
    )
    try:
        with pytest.raises(type(failure)):
            asyncio.run(service.generate(AIRequest((AIMessage("user", "question"),))))
        assert len(primary.requests) == 1
        assert fallback.requests == []
    finally:
        database.dispose()


def test_exponential_backoff_is_capped_and_attempt_count_bounded(monkeypatch) -> None:
    database = make_database()
    provider = FakeProvider(
        "openrouter",
        "primary",
        [
            AIProviderUnavailableError(),
            AIProviderUnavailableError(),
            AIProviderUnavailableError(),
            AIProviderUnavailableError(),
        ],
    )
    settings = Settings(
        llm_primary_provider="openrouter",
        llm_primary_model="primary",
        llm_primary_model_cost="free",
        llm_max_retries=3,
        llm_retry_base_delay_seconds=0.5,
        llm_retry_max_delay_seconds=0.75,
    )
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr("app.services.ai_generation.asyncio.sleep", fake_sleep)
    service = AIGenerationService(
        settings,
        database,
        [ModelRoute("openrouter", "primary", "free", provider)],
    )
    try:
        with pytest.raises(AIProviderUnavailableError):
            asyncio.run(service.generate(AIRequest((AIMessage("user", "question"),))))
        assert len(provider.requests) == 4
        assert delays == [0.5, 0.75, 0.75]
    finally:
        database.dispose()


def test_paid_gate_and_monthly_cap_block_provider_calls() -> None:
    database = make_database()
    paid = FakeProvider("openrouter", "paid-model", [successful_result("openrouter", "paid-model")])
    disabled_service = AIGenerationService(
        Settings(
            llm_primary_provider="openrouter",
            llm_primary_model="paid-model",
            llm_primary_model_cost="paid",
        ),
        database,
        [ModelRoute("openrouter", "paid-model", "paid", paid)],
    )
    with pytest.raises(AIPaidUsageDisabledError):
        asyncio.run(disabled_service.generate(AIRequest((AIMessage("user", "question"),))))
    assert paid.requests == []
    with database.session() as session:
        disabled_audit = session.scalar(select(ProviderAudit))
        assert disabled_audit is not None and disabled_audit.cost_tier == "paid"

    now = datetime.now(timezone.utc)
    month_start = date(now.year, now.month, 1)
    with database.session() as session:
        reservation = PaidBudgetRepository.reserve(
            session,
            month_start=month_start,
            cap_usd=Decimal("0.05"),
            minimum_remaining_usd=Decimal("0.01"),
        )
        assert reservation is not None
        PaidBudgetRepository.settle(
            session,
            reservation,
            actual_cost_usd=Decimal("0.05"),
        )
    capped_service = AIGenerationService(
        Settings(
            llm_primary_provider="openrouter",
            llm_primary_model="paid-model",
            llm_primary_model_cost="paid",
            llm_paid_enabled=True,
            llm_monthly_cap_usd=Decimal("0.05"),
            llm_paid_minimum_remaining_usd=Decimal("0.01"),
        ),
        database,
        [ModelRoute("openrouter", "paid-model", "paid", paid)],
    )
    try:
        with pytest.raises(AIBudgetExceededError):
            asyncio.run(capped_service.generate(AIRequest((AIMessage("user", "question"),))))
        assert paid.requests == []
    finally:
        database.dispose()


@pytest.mark.parametrize(
    "reported_cost",
    [None, Decimal("-0.001"), Decimal("NaN"), "not-a-cost"],
)
def test_unknown_paid_cost_returns_answer_and_blocks_later_paid_calls(
    reported_cost: object,
) -> None:
    database = make_database()
    first = FakeProvider(
        "openrouter",
        "paid-model",
        [successful_result("openrouter", "paid-model", reported_cost)],  # type: ignore[arg-type]
    )
    settings = Settings(
        llm_primary_provider="openrouter",
        llm_primary_model="paid-model",
        llm_primary_model_cost="paid",
        llm_paid_enabled=True,
        llm_monthly_cap_usd=Decimal("0.01"),
        llm_paid_minimum_remaining_usd=Decimal("0.002"),
    )
    service = AIGenerationService(
        settings,
        database,
        [ModelRoute("openrouter", "paid-model", "paid", first)],
    )
    try:
        result = asyncio.run(service.generate(AIRequest((AIMessage("user", "question"),))))
        assert result.text == "safe answer"
        assert len(first.requests) == 1
        with database.session() as session:
            budget = session.get(
                AIPaidMonthlyBudget,
                datetime.now(timezone.utc).date().replace(day=1),
            )
            audit = session.scalar(select(ProviderAudit).where(ProviderAudit.outcome == "success"))
            reservation_row = session.scalar(select(AIPaidBudgetReservation))
            assert budget is not None and budget.unknown_cost is True
            assert budget.reserved_usd == Decimal("0.010000000000")
            assert audit is not None and audit.cost_tier == "paid"
            assert audit.reported_cost_usd is None
            assert reservation_row is not None and reservation_row.status == "unknown"

        later = FakeProvider(
            "openrouter",
            "paid-model",
            [successful_result("openrouter", "paid-model", Decimal("0.001"))],
        )
        later_service = AIGenerationService(
            settings,
            database,
            [ModelRoute("openrouter", "paid-model", "paid", later)],
        )
        with pytest.raises(AIBudgetExceededError):
            asyncio.run(later_service.generate(AIRequest((AIMessage("user", "later"),))))
        assert later.requests == []
    finally:
        database.dispose()


def test_paid_budget_reservation_is_atomic_for_concurrent_calls() -> None:
    database = make_database()
    entered_provider = asyncio.Event()
    release_provider = asyncio.Event()

    class WaitingProvider(FakeProvider):
        async def generate(self, request: AIRequest) -> AIResult:
            self.requests.append(request)
            entered_provider.set()
            await release_provider.wait()
            return successful_result(self.provider_name, self.model, Decimal("0.006"))

    settings = Settings(
        llm_primary_provider="openrouter",
        llm_primary_model="paid-model",
        llm_primary_model_cost="paid",
        llm_paid_enabled=True,
        llm_monthly_cap_usd=Decimal("0.01"),
        llm_paid_minimum_remaining_usd=Decimal("0.002"),
    )
    first_provider = WaitingProvider("openrouter", "paid-model", [])
    second_provider = WaitingProvider("openrouter", "paid-model", [])
    first_service = AIGenerationService(
        settings,
        database,
        [ModelRoute("openrouter", "paid-model", "paid", first_provider)],
    )
    second_service = AIGenerationService(
        settings,
        database,
        [ModelRoute("openrouter", "paid-model", "paid", second_provider)],
    )

    async def execute() -> list[object]:
        first_task = asyncio.create_task(
            first_service.generate(AIRequest((AIMessage("user", "first"),)))
        )
        await entered_provider.wait()
        second_task = asyncio.create_task(
            second_service.generate(AIRequest((AIMessage("user", "second"),)))
        )
        await asyncio.sleep(0)
        release_provider.set()
        return await asyncio.gather(first_task, second_task, return_exceptions=True)

    try:
        outcomes = asyncio.run(execute())
        assert sum(isinstance(outcome, AIResult) for outcome in outcomes) == 1
        assert sum(isinstance(outcome, AIBudgetExceededError) for outcome in outcomes) == 1
        assert len(first_provider.requests) + len(second_provider.requests) == 1
        with database.session() as session:
            budget = session.scalar(select(AIPaidMonthlyBudget))
            assert budget is not None
            assert budget.spent_usd == Decimal("0.006000000000")
            assert budget.reserved_usd == Decimal("0E-12")
    finally:
        database.dispose()


def test_free_tier_audit_cost_does_not_consume_paid_budget() -> None:
    database = make_database()
    with database.session() as session:
        ProviderAuditRepository.record(
            session,
            provider="openrouter",
            model="free-model",
            outcome="success",
            cost_tier="free",
            reported_cost_usd=Decimal("0.009"),
        )
        session.commit()
    provider = FakeProvider(
        "openrouter",
        "paid-model",
        [successful_result("openrouter", "paid-model", Decimal("0.006"))],
    )
    settings = Settings(
        llm_primary_provider="openrouter",
        llm_primary_model="paid-model",
        llm_primary_model_cost="paid",
        llm_paid_enabled=True,
        llm_monthly_cap_usd=Decimal("0.01"),
        llm_paid_minimum_remaining_usd=Decimal("0.002"),
    )
    service = AIGenerationService(
        settings,
        database,
        [ModelRoute("openrouter", "paid-model", "paid", provider)],
    )
    try:
        result = asyncio.run(service.generate(AIRequest((AIMessage("user", "paid question"),))))
        assert result.text == "safe answer"
        assert len(provider.requests) == 1
        with database.session() as session:
            audit = session.scalar(select(ProviderAudit).where(ProviderAudit.model == "paid-model"))
            assert audit is not None and audit.cost_tier == "paid"
    finally:
        database.dispose()


def test_sequential_paid_calls_reserve_remaining_and_minimum_blocks_remainder() -> None:
    database = make_database()
    settings = Settings(
        llm_primary_provider="openrouter",
        llm_primary_model="paid-model",
        llm_primary_model_cost="paid",
        llm_paid_enabled=True,
        llm_monthly_cap_usd=Decimal("0.01"),
        llm_paid_minimum_remaining_usd=Decimal("0.002"),
    )
    providers = [
        FakeProvider(
            "openrouter",
            "paid-model",
            [successful_result("openrouter", "paid-model", Decimal("0.006"))],
        ),
        FakeProvider(
            "openrouter",
            "paid-model",
            [successful_result("openrouter", "paid-model", Decimal("0.003"))],
        ),
        FakeProvider(
            "openrouter",
            "paid-model",
            [successful_result("openrouter", "paid-model", Decimal("0.0005"))],
        ),
    ]
    try:
        for index, provider in enumerate(providers):
            service = AIGenerationService(
                settings,
                database,
                [ModelRoute("openrouter", "paid-model", "paid", provider)],
            )
            request = AIRequest((AIMessage("user", f"question {index}"),))
            if index < 2:
                result = asyncio.run(service.generate(request))
                assert result.text == "safe answer"
                assert len(provider.requests) == 1
            else:
                with pytest.raises(AIBudgetExceededError):
                    asyncio.run(service.generate(request))
                assert provider.requests == []

        with database.session() as session:
            budget = session.scalar(select(AIPaidMonthlyBudget))
            reservations = session.scalars(
                select(AIPaidBudgetReservation).order_by(AIPaidBudgetReservation.created_at)
            ).all()
            assert budget is not None
            assert budget.spent_usd == Decimal("0.009000000000")
            assert budget.reserved_usd == Decimal("0E-12")
            assert [reservation.status for reservation in reservations] == ["settled", "settled"]
    finally:
        database.dispose()


def test_unsettled_reservation_survives_restart_and_fails_closed() -> None:
    database = make_database()
    now = datetime.now(timezone.utc)
    with database.session() as session:
        reservation = PaidBudgetRepository.reserve(
            session,
            month_start=date(now.year, now.month, 1),
            cap_usd=Decimal("0.01"),
            minimum_remaining_usd=Decimal("0.001"),
        )
        assert reservation is not None
    restarted_provider = FakeProvider(
        "openrouter",
        "paid-model",
        [successful_result("openrouter", "paid-model", Decimal("0.001"))],
    )
    service = AIGenerationService(
        Settings(
            llm_primary_provider="openrouter",
            llm_primary_model="paid-model",
            llm_primary_model_cost="paid",
            llm_paid_enabled=True,
            llm_monthly_cap_usd=Decimal("0.01"),
            llm_paid_minimum_remaining_usd=Decimal("0.001"),
        ),
        database,
        [ModelRoute("openrouter", "paid-model", "paid", restarted_provider)],
    )
    try:
        with pytest.raises(AIBudgetExceededError):
            asyncio.run(service.generate(AIRequest((AIMessage("user", "question"),))))
        assert restarted_provider.requests == []
        with database.session() as session:
            row = session.get(AIPaidBudgetReservation, reservation.id)
            assert row is not None and row.status == "reserved"
    finally:
        database.dispose()


def test_free_route_succeeds_and_audits_without_prompt_or_response_storage() -> None:
    database = make_database()
    provider = FakeProvider(
        "gemini",
        "free-model",
        [successful_result("gemini", "free-model")],
    )
    service = AIGenerationService(
        Settings(llm_primary_provider="gemini", llm_primary_model="free-model", llm_primary_model_cost="free"),
        database,
        [ModelRoute("gemini", "free-model", "free", provider)],
    )
    try:
        result = asyncio.run(service.generate(AIRequest((AIMessage("user", "private prompt"),))))
        assert result.text == "safe answer"
        with database.session() as session:
            row = session.scalar(select(ProviderAudit))
            assert row is not None
            assert row.outcome == "success"
            assert row.provider == "gemini"
            assert row.model == "free-model"
            assert row.reported_cost_usd is None
            assert not hasattr(row, "prompt")
            assert not hasattr(row, "response")
    finally:
        database.dispose()


def test_audit_failure_does_not_return_provider_success() -> None:
    database = Database(None)
    provider = FakeProvider("openrouter", "free-model", [successful_result("openrouter", "free-model")])
    service = AIGenerationService(
        Settings(),
        database,
        [ModelRoute("openrouter", "free-model", "free", provider)],
    )
    with pytest.raises(AIAuditPersistenceError):
        asyncio.run(service.generate(AIRequest((AIMessage("user", "question"),))))
    assert provider.requests == []


def test_health_summary_redacts_credentials(tmp_path: Path) -> None:
    database = make_database()
    provider = FakeProvider("openrouter", "safe/model-id", [successful_result("openrouter", "safe/model-id")])
    service = AIGenerationService(
        Settings(llm_openrouter_api_key="not-for-health"),
        database,
        [ModelRoute("openrouter", "safe/model-id", "free", provider)],
    )
    app = create_app(
        Settings(rules_refresh_mode="external"),
        card_provider=ScryfallProvider(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"object": "catalog"}, request=request)
            )
        ),
        rules_service=offline_rules_service(tmp_path),
        ai_generation_service=service,
    )
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json()["ai"] == {
            "status": "ok",
            "providers": [
                {"provider": "openrouter", "model": "safe/model-id", "availability": "configured"}
            ],
        }
        assert "not-for-health" not in response.text
    finally:
        # TestClient lifespan disposes the app's own empty DB, not this injected audit database.
        database.dispose()


def test_settings_require_cost_classification_and_limit_paid_cap() -> None:
    with pytest.raises(ValueError):
        Settings(llm_primary_provider="gemini", llm_primary_model="model-without-tier")
    with pytest.raises(ValueError):
        Settings(
            llm_primary_provider="gemini",
            llm_primary_model="paid",
            llm_primary_model_cost="paid",
            llm_paid_enabled=True,
            llm_monthly_cap_usd=Decimal("5.01"),
        )
    with pytest.raises(ValueError):
        Settings(
            llm_monthly_cap_usd=Decimal("0.01"),
            llm_paid_minimum_remaining_usd=Decimal("0.02"),
        )
    with pytest.raises(ValueError):
        Settings(llm_paid_minimum_remaining_usd=Decimal("0"))

