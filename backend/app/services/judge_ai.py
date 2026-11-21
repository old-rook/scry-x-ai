from abc import ABC, abstractmethod
import asyncio
import json
from collections.abc import Awaitable, Callable

import httpx

from .builtin_rules import answer_for_question
from ..core.config import Settings


class LLMClient(ABC):
    @abstractmethod
    async def generate_judge_answer(self, *, question: str, context: dict) -> dict:
        raise NotImplementedError


class MockLLMClient(LLMClient):
    async def generate_judge_answer(self, *, question: str, context: dict) -> dict:
        grounded_answer = answer_for_question(question, context["rules"])
        if grounded_answer:
            return grounded_answer
        if not context["rules"]:
            return {
                "status": "insufficient_evidence",
                "summary": "I couldn't find relevant rules in the active dataset.",
                "explanation": [],
                "assumptions": [],
                "citations": [],
                "uncertainties": [
                    "The local dataset contains curated excerpts. Ingest the current Comprehensive Rules to search beyond the supported topics."
                ],
                "clarifying_question": "Can you provide the relevant card text or specify the game situation?",
            }
        return {
            "status": "insufficient_evidence",
            "summary": "Relevant rules were found, but I can't safely apply them to this situation yet.",
            "explanation": [
                f"Comprehensive Rules {rule['rule_id']} ({rule['section'] or 'General'}): {rule['text']}"
                for rule in context["rules"][:3]
            ],
            "assumptions": [],
            "citations": [
                {
                    "evidence_id": rule["evidence_id"],
                    "kind": "comprehensive_rule",
                    "reason": "This retrieved rule may be relevant to the question.",
                }
                for rule in context["rules"][:3]
            ],
            "uncertainties": ["This local answer mode only explains interactions for which it has a specific rule-grounded response."],
            "clarifying_question": None,
        }


class OpenAICompatibleLLMClient(LLMClient):
    def __init__(self, *, api_key: str, model: str, base_url: str, timeout: float = 30.0):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def generate_judge_answer(self, *, question: str, context: dict) -> dict:
        system_prompt = (
            "You are a careful Magic: The Gathering rules research assistant, not an official judge. "
            "A question may be about general rules or keywords and may not name a card; do not require "
            "a card reference unless card text is necessary to answer. Answer only from the supplied "
            "evidence. Explain how each cited rule applies, identify "
            "missing assumptions, and do not invent card text, rulings, quotations, or rule numbers. "
            "Citations must use evidence_id values present in the context and the matching evidence kind. "
            "If evidence is insufficient, say so. Return only a JSON object with status, summary, "
            "explanation (array), assumptions (array), citations (array of evidence_id, kind, reason), "
            "uncertainties (array), and clarifying_question (string or null)."
        )
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {
                            "role": "user",
                            "content": json.dumps(
                                {"question": question, "evidence": context},
                                ensure_ascii=False,
                            ),
                        },
                    ],
                },
            )
        response.raise_for_status()
        payload = response.json()
        return json.loads(payload["choices"][0]["message"]["content"])


class ResilientLLMClient(LLMClient):
    transient_status_codes = {408, 425, 429, 500, 502, 503, 504}

    def __init__(
        self,
        *,
        primary: LLMClient,
        fallbacks: list[LLMClient],
        max_primary_attempts: int = 3,
        base_backoff_seconds: float = 1.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self.primary = primary
        self.fallbacks = fallbacks
        self.max_primary_attempts = max_primary_attempts
        self.base_backoff_seconds = base_backoff_seconds
        self.sleep = sleep

    async def generate_judge_answer(self, *, question: str, context: dict) -> dict:
        last_error: Exception | None = None
        providers = [self.primary, *self.fallbacks]

        for provider_index, provider in enumerate(providers):
            attempts = self.max_primary_attempts if provider_index == 0 else 1
            for attempt in range(attempts):
                try:
                    return await provider.generate_judge_answer(
                        question=question,
                        context=context,
                    )
                except (httpx.HTTPError, KeyError, ValueError) as exc:
                    last_error = exc
                    retry = (
                        provider_index == 0
                        and attempt + 1 < attempts
                        and self._is_transient(exc)
                    )
                    if retry:
                        await self.sleep(self.base_backoff_seconds * (2**attempt))
                    else:
                        break

        if last_error:
            raise last_error
        raise RuntimeError("No LLM provider was configured")

    def _is_transient(self, error: Exception) -> bool:
        if isinstance(error, httpx.HTTPStatusError):
            return error.response.status_code in self.transient_status_codes
        return isinstance(error, (httpx.TimeoutException, httpx.NetworkError))


def build_llm_client(settings: Settings) -> LLMClient:
    if settings.llm_provider == "mock":
        return MockLLMClient()

    primary = OpenAICompatibleLLMClient(
        api_key=settings.llm_api_key or "",
        model=settings.llm_model,
        base_url=settings.llm_base_url,
    )
    fallbacks = [
        OpenAICompatibleLLMClient(
            api_key=settings.llm_api_key or "",
            model=model,
            base_url=settings.llm_base_url,
        )
        for model in settings.fallback_model_ids
    ]
    fallbacks.extend(
        OpenAICompatibleLLMClient(
            api_key=settings.openrouter_api_key or "",
            model=model,
            base_url=settings.openrouter_base_url,
        )
        for model in settings.openrouter_fallback_model_ids
    )
    return ResilientLLMClient(primary=primary, fallbacks=fallbacks)
