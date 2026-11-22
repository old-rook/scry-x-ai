from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Literal, Protocol


class AIErrorClass(StrEnum):
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    AUTHENTICATION = "authentication"
    CONFIGURATION = "configuration"
    CONTEXT_TOO_LARGE = "context_too_large"
    INVALID_REQUEST = "invalid_request"
    INVALID_RESPONSE = "invalid_response"
    UNKNOWN = "unknown"


class AIProviderError(Exception):
    classification = AIErrorClass.UNKNOWN
    failover_eligible = False

    def __init__(self) -> None:
        super().__init__(self.classification.value)


class AITimeoutError(AIProviderError):
    classification = AIErrorClass.TIMEOUT
    failover_eligible = True


class AIRateLimitError(AIProviderError):
    classification = AIErrorClass.RATE_LIMIT
    failover_eligible = True


class AIProviderUnavailableError(AIProviderError):
    classification = AIErrorClass.PROVIDER_UNAVAILABLE
    failover_eligible = True


class AIAuthenticationError(AIProviderError):
    classification = AIErrorClass.AUTHENTICATION


class AIConfigurationError(AIProviderError):
    classification = AIErrorClass.CONFIGURATION


class AIContextTooLargeError(AIProviderError):
    classification = AIErrorClass.CONTEXT_TOO_LARGE


class AIInvalidRequestError(AIProviderError):
    classification = AIErrorClass.INVALID_REQUEST


class AIInvalidResponseError(AIProviderError):
    classification = AIErrorClass.INVALID_RESPONSE


class AIUnknownProviderError(AIProviderError):
    classification = AIErrorClass.UNKNOWN


class AIPaidUsageDisabledError(AIConfigurationError):
    pass


class AIBudgetExceededError(AIConfigurationError):
    pass


class AIAuditPersistenceError(Exception):
    """Audit persistence failure; generation must not return success without an audit."""


@dataclass(frozen=True)
class AIMessage:
    role: str
    content: str


@dataclass(frozen=True)
class AIRequest:
    messages: tuple[AIMessage, ...]
    max_output_tokens: int = 1024


@dataclass(frozen=True)
class AIUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    reported_cost_usd: Decimal | None = None


@dataclass(frozen=True)
class AIResult:
    provider: str
    model: str
    text: str
    usage: AIUsage


class AIProvider(Protocol):
    provider_name: str
    model: str
    configured: bool

    async def generate(self, request: AIRequest) -> AIResult: ...

    def health(self) -> Literal["configured", "unavailable"]: ...

    async def close(self) -> None: ...
