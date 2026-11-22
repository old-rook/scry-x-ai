from typing import Literal

import httpx
from pydantic import SecretStr

from app.providers.ai import AIConfigurationError, AIInvalidResponseError, AIRequest, AIResult, AIUsage
from app.providers.ai_http import parse_response, safe_provider_error, usage_values


class GeminiProvider:
    provider_name = "gemini"

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
            base_url="https://generativelanguage.googleapis.com/v1beta",
            timeout=httpx.Timeout(timeout),
            transport=transport,
        )

    def health(self) -> Literal["configured", "unavailable"]:
        return "configured" if self.configured else "unavailable"

    async def generate(self, request: AIRequest) -> AIResult:
        if not self.configured or self._api_key is None:
            raise AIConfigurationError()
        system_parts = [message.content for message in request.messages if message.role == "system"]
        contents = [
            {
                "role": "model" if message.role == "assistant" else "user",
                "parts": [{"text": message.content}],
            }
            for message in request.messages
            if message.role != "system"
        ]
        generation_config: dict[str, object] = {
            "maxOutputTokens": request.max_output_tokens
        }
        if request.response_format == "json_object":
            generation_config["responseMimeType"] = "application/json"
        body: dict[str, object] = {
            "contents": contents,
            "generationConfig": generation_config,
        }
        if system_parts:
            body["systemInstruction"] = {"parts": [{"text": "\n".join(system_parts)}]}
        try:
            response = await self._client.post(
                f"/models/{self.model}:generateContent",
                headers={"x-goog-api-key": self._api_key.get_secret_value()},
                json=body,
            )
        except (httpx.HTTPError, ValueError) as error:
            raise safe_provider_error(error) from None
        payload = parse_response(response)
        try:
            text = payload["candidates"][0]["content"]["parts"][0]["text"]
            if not isinstance(text, str) or not text:
                raise ValueError
        except (KeyError, IndexError, TypeError, ValueError):
            raise AIInvalidResponseError() from None
        input_tokens, output_tokens, cost = usage_values(payload, openrouter=False)
        return AIResult(self.provider_name, self.model, text, AIUsage(input_tokens, output_tokens, cost))

    async def close(self) -> None:
        await self._client.aclose()
