import json
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.providers.ai import (
    AIAuthenticationError,
    AIContextTooLargeError,
    AIInvalidRequestError,
    AIInvalidResponseError,
    AIRateLimitError,
    AIProviderError,
    AIProviderUnavailableError,
    AITimeoutError,
    AIUnknownProviderError,
)


def parse_response(response: httpx.Response) -> dict[str, Any]:
    if response.status_code in {401, 403}:
        raise AIAuthenticationError()
    if response.status_code == 429:
        raise AIRateLimitError()
    if response.status_code in {408, 504}:
        raise AITimeoutError()
    if response.status_code == 413:
        raise AIContextTooLargeError()
    if response.status_code >= 500:
        raise AIProviderUnavailableError()

    try:
        payload = response.json()
    except (ValueError, json.JSONDecodeError):
        raise AIInvalidResponseError() from None
    if response.is_error:
        # Inspect provider error fields only to classify; never expose or log the body.
        serialized = json.dumps(payload, ensure_ascii=True).lower() if isinstance(payload, dict) else ""
        if "context" in serialized and any(
            word in serialized for word in ("large", "length", "token")
        ):
            raise AIContextTooLargeError()
        if response.status_code == 400:
            raise AIInvalidRequestError()
        if response.status_code == 404:
            raise AIInvalidRequestError()
        raise AIUnknownProviderError()
    if not isinstance(payload, dict):
        raise AIInvalidResponseError()
    return payload


def usage_values(
    payload: dict[str, Any],
    *,
    openrouter: bool,
) -> tuple[int | None, int | None, Decimal | None]:
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        usage = payload.get("usageMetadata")
    if not isinstance(usage, dict):
        return None, None, None

    input_count = usage.get("prompt_tokens", usage.get("promptTokenCount"))
    output_count = usage.get("completion_tokens", usage.get("candidatesTokenCount"))
    input_tokens = input_count if type(input_count) is int and input_count >= 0 else None
    output_tokens = output_count if type(output_count) is int and output_count >= 0 else None
    cost: Decimal | None = None
    if openrouter and usage.get("cost") is not None:
        try:
            parsed_cost = Decimal(str(usage["cost"]))
            if parsed_cost.is_finite() and parsed_cost >= 0:
                cost = parsed_cost
        except (InvalidOperation, ValueError):
            pass
    return input_tokens, output_tokens, cost


def map_transport_error(error: Exception) -> AIProviderError:
    if isinstance(error, httpx.TimeoutException):
        return AITimeoutError()
    if isinstance(error, (httpx.NetworkError, httpx.RemoteProtocolError)):
        return AIProviderUnavailableError()
    return AIUnknownProviderError()


def safe_provider_error(error: Exception) -> AIProviderError:
    # Do not chain httpx exceptions: their messages may include URLs or request data.
    mapped = map_transport_error(error)
    mapped.__suppress_context__ = True
    return mapped
