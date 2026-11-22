from decimal import Decimal
from typing import Literal

import httpx
from pydantic import SecretStr

from app.providers.ai import (
    AIConfigurationError,
    AIInvalidResponseError,
    AIRequest,
    AIResult,
    AIUsage,
)
from app.providers.ai_http import parse_response, safe_provider_error, usage_values


_TOKENS_PER_MILLION = Decimal("1000000")


class OpenAIProvider:
    provider_name = "openai"

    def __init__(
        self,
        model: str,
        api_key: SecretStr | None,
        *,
        input_price_per_million_usd: Decimal,
        cached_input_price_per_million_usd: Decimal,
        output_price_per_million_usd: Decimal,
        timeout: float = 20,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.model = model
        self._api_key = SecretStr(api_key) if isinstance(api_key, str) else api_key
        self._input_price = input_price_per_million_usd
        self._cached_input_price = cached_input_price_per_million_usd
        self._output_price = output_price_per_million_usd
        self.configured = (
            self._api_key is not None
            and bool(self._api_key.get_secret_value().strip())
        )
        self._client = httpx.AsyncClient(
            base_url="https://api.openai.com/v1",
            timeout=httpx.Timeout(timeout),
            transport=transport,
        )

    def health(self) -> Literal["configured", "unavailable"]:
        return "configured" if self.configured else "unavailable"

    async def generate(self, request: AIRequest) -> AIResult:
        if not self.configured or self._api_key is None:
            raise AIConfigurationError()
        try:
            response = await self._client.post(
                "/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key.get_secret_value()}"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": message.role, "content": message.content}
                        for message in request.messages
                    ],
                    "max_completion_tokens": request.max_output_tokens,
                },
            )
        except (httpx.HTTPError, ValueError) as error:
            raise safe_provider_error(error) from None
        payload = parse_response(response)
        try:
            text = payload["choices"][0]["message"]["content"]
            if not isinstance(text, str) or not text:
                raise ValueError
        except (KeyError, IndexError, TypeError, ValueError):
            raise AIInvalidResponseError() from None

        input_tokens, output_tokens, _ = usage_values(payload, openrouter=False)
        reported_cost = self._reported_cost(
            payload,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        return AIResult(
            self.provider_name,
            self.model,
            text,
            AIUsage(input_tokens, output_tokens, reported_cost),
        )

    def _reported_cost(
        self,
        payload: dict[str, object],
        *,
        input_tokens: int | None,
        output_tokens: int | None,
    ) -> Decimal | None:
        prices = (
            self._input_price,
            self._cached_input_price,
            self._output_price,
        )
        if (
            input_tokens is None
            or output_tokens is None
            or input_tokens < 0
            or output_tokens < 0
            or any(not price.is_finite() or price <= 0 for price in prices)
        ):
            return None

        usage = payload.get("usage")
        if not isinstance(usage, dict):
            return None
        prompt_details = usage.get("prompt_tokens_details")
        cached_tokens = 0
        if isinstance(prompt_details, dict) and "cached_tokens" in prompt_details:
            candidate = prompt_details["cached_tokens"]
            if type(candidate) is not int or candidate < 0 or candidate > input_tokens:
                return None
            cached_tokens = candidate

        uncached_tokens = input_tokens - cached_tokens
        cost = (
            Decimal(uncached_tokens) * self._input_price
            + Decimal(cached_tokens) * self._cached_input_price
            + Decimal(output_tokens) * self._output_price
        )
        return cost / _TOKENS_PER_MILLION

    async def close(self) -> None:
        await self._client.aclose()
