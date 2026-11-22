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


class OpenRouterProvider:
    provider_name = "openrouter"

    def __init__(
        self,
        model: str,
        api_key: SecretStr | None,
        *,
        timeout: float = 20,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.model = model
        self._api_key = SecretStr(api_key) if isinstance(api_key, str) else api_key
        self.configured = (
            self._api_key is not None
            and bool(self._api_key.get_secret_value().strip())
        )
        self._client = httpx.AsyncClient(
            base_url="https://openrouter.ai/api/v1",
            timeout=httpx.Timeout(timeout),
            transport=transport,
        )

    def health(self) -> Literal["configured", "unavailable"]:
        return "configured" if self.configured else "unavailable"

    async def generate(self, request: AIRequest) -> AIResult:
        if not self.configured or self._api_key is None:
            raise AIConfigurationError()
        body: dict[str, object] = {
            "model": self.model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in request.messages
            ],
            "max_tokens": request.max_output_tokens,
        }
        if request.response_format == "json_object":
            body["response_format"] = {"type": "json_object"}
        try:
            response = await self._client.post(
                "/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key.get_secret_value()}"},
                json=body,
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
        input_tokens, output_tokens, cost = usage_values(payload, openrouter=True)
        return AIResult(self.provider_name, self.model, text, AIUsage(input_tokens, output_tokens, cost))

    async def close(self) -> None:
        await self._client.aclose()
