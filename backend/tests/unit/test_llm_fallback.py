import httpx
import pytest

from app.core.config import Settings
from app.services.judge_ai import (
    LLMClient,
    OpenAICompatibleLLMClient,
    ResilientLLMClient,
    build_llm_client,
)


class FakeLLMClient(LLMClient):
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = 0

    async def generate_judge_answer(self, *, question: str, context: dict) -> dict:
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


def service_unavailable() -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://provider.example/chat/completions")
    response = httpx.Response(503, request=request)
    return httpx.HTTPStatusError("service unavailable", request=request, response=response)


@pytest.mark.asyncio
async def test_retries_primary_three_times_then_uses_fallback_in_order():
    primary = FakeLLMClient(error=service_unavailable())
    first_fallback = FakeLLMClient(error=service_unavailable())
    second_fallback = FakeLLMClient(result={"summary": "Fallback answer"})
    waits = []

    async def record_wait(seconds: float):
        waits.append(seconds)

    client = ResilientLLMClient(
        primary=primary,
        fallbacks=[first_fallback, second_fallback],
        sleep=record_wait,
    )
    answer = await client.generate_judge_answer(question="Question?", context={})

    assert answer == {"summary": "Fallback answer"}
    assert primary.calls == 3
    assert first_fallback.calls == 1
    assert second_fallback.calls == 1
    assert waits == [1.0, 2.0]


@pytest.mark.asyncio
async def test_does_not_retry_primary_after_non_transient_status():
    request = httpx.Request("POST", "https://provider.example/chat/completions")
    response = httpx.Response(400, request=request)
    primary = FakeLLMClient(
        error=httpx.HTTPStatusError("bad request", request=request, response=response)
    )
    first_fallback = FakeLLMClient(result={"summary": "Fallback answer"})
    waits = []

    async def record_wait(seconds: float):
        waits.append(seconds)

    client = ResilientLLMClient(
        primary=primary,
        fallbacks=[first_fallback],
        sleep=record_wait,
    )
    answer = await client.generate_judge_answer(question="Question?", context={})

    assert answer == {"summary": "Fallback answer"}
    assert primary.calls == 1
    assert first_fallback.calls == 1
    assert waits == []


def test_settings_provide_two_fallback_models_and_exclude_primary():
    settings = Settings(
        _env_file=None,
        llm_provider="openai-compatible",
        llm_api_key="test-key",
        llm_model="gemini-4-hydrogen",
    )

    assert settings.fallback_model_ids == ["gemini-4-neon", "gemini-3.6-flash"]
    settings.validate_required()


def test_settings_require_two_distinct_fallback_models():
    settings = Settings(
        _env_file=None,
        llm_provider="openai-compatible",
        llm_api_key="test-key",
        llm_model="gemini-4-hydrogen",
        llm_fallback_models="gemini-4-neon",
    )

    with pytest.raises(RuntimeError, match="at least two"):
        settings.validate_required()


def test_openrouter_fallbacks_require_a_separate_api_key():
    settings = Settings(
        _env_file=None,
        llm_provider="openai-compatible",
        llm_api_key="gemini-key",
        llm_model="gemini-2.5-flash",
        openrouter_fallback_models="google/gemma-4-31b-it:free",
    )

    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        settings.validate_required()


def test_factory_routes_openrouter_fallbacks_to_separate_endpoint_and_key():
    settings = Settings(
        _env_file=None,
        llm_provider="openai-compatible",
        llm_api_key="gemini-key",
        llm_model="gemini-2.5-flash",
        llm_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        llm_fallback_models="gemini-3.8-flash,gemini-3.6-flash",
        openrouter_api_key="openrouter-key",
        openrouter_base_url="https://openrouter.ai/api/v1",
        openrouter_fallback_models=(
            "google/gemma-4-31b-it:free,baidu/ernie-5.5-flash-preview:free,openrouter/free"
        ),
    )
    settings.validate_required()

    client = build_llm_client(settings)

    assert isinstance(client, ResilientLLMClient)
    assert [fallback.model for fallback in client.fallbacks] == [
        "gemini-3.8-flash",
        "gemini-3.6-flash",
        "google/gemma-4-31b-it:free",
        "baidu/ernie-5.5-flash-preview:free",
        "openrouter/free",
    ]
    assert all(
        fallback.base_url == "https://generativelanguage.googleapis.com/v1beta/openai"
        for fallback in client.fallbacks[:2]
    )
    assert all(
        fallback.api_key == "openrouter-key"
        and fallback.base_url == "https://openrouter.ai/api/v1"
        for fallback in client.fallbacks[2:]
    )
    assert isinstance(client.primary, OpenAICompatibleLLMClient)
    assert client.primary.model == "gemini-2.5-flash"
