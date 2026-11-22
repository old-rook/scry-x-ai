from pathlib import Path
from decimal import Decimal
import re
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings import NoDecode


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Scry-X-AI"
    app_version: str = "0.1.0"
    database_url: SecretStr | None = None
    jwt_signing_key: SecretStr | None = None
    rules_storage_dir: Path = Path(__file__).resolve().parents[2] / "data" / "rules"
    rules_refresh_mode: Literal["local", "external"] = "local"
    rules_refresh_interval_hours: int = Field(default=24, ge=1, le=24)
    access_token_lifetime_minutes: int = Field(default=15, ge=15, le=15)
    app_environment: Literal["development", "test", "staging", "production"] = Field(
        default="development",
        validation_alias="APP_ENV",
    )
    api_v1_prefix: str = "/api/v1"
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]
    llm_openrouter_api_key: SecretStr | None = Field(
        default=None, validation_alias="LLM_OPENROUTER_API_KEY"
    )
    llm_gemini_api_key: SecretStr | None = Field(
        default=None, validation_alias="LLM_GEMINI_API_KEY"
    )
    llm_openai_api_key: SecretStr | None = Field(
        default=None, validation_alias="LLM_OPENAI_API_KEY"
    )
    llm_openai_pricing_model: str | None = Field(
        default=None, validation_alias="LLM_OPENAI_PRICING_MODEL"
    )
    llm_openai_input_price_per_million_usd: Decimal = Field(
        default=Decimal("0.15"),
        validation_alias="LLM_OPENAI_INPUT_PRICE_PER_MILLION_USD",
        gt=0,
    )
    llm_openai_cached_input_price_per_million_usd: Decimal = Field(
        default=Decimal("0.075"),
        validation_alias="LLM_OPENAI_CACHED_INPUT_PRICE_PER_MILLION_USD",
        gt=0,
    )
    llm_openai_output_price_per_million_usd: Decimal = Field(
        default=Decimal("0.60"),
        validation_alias="LLM_OPENAI_OUTPUT_PRICE_PER_MILLION_USD",
        gt=0,
    )
    llm_primary_provider: Literal["openrouter", "gemini", "openai"] | None = Field(
        default=None, validation_alias="LLM_PRIMARY_PROVIDER"
    )
    llm_primary_model: str | None = Field(default=None, validation_alias="LLM_PRIMARY_MODEL")
    llm_primary_model_cost: Literal["free", "paid"] | None = Field(
        default=None, validation_alias="LLM_PRIMARY_MODEL_COST"
    )
    llm_fallback_provider: Literal["openrouter", "gemini", "openai"] | None = Field(
        default=None, validation_alias="LLM_FALLBACK_PROVIDER"
    )
    llm_fallback_model: str | None = Field(default=None, validation_alias="LLM_FALLBACK_MODEL")
    llm_fallback_model_cost: Literal["free", "paid"] | None = Field(
        default=None, validation_alias="LLM_FALLBACK_MODEL_COST"
    )
    llm_paid_enabled: bool = Field(default=False, validation_alias="LLM_PAID_ENABLED")
    llm_monthly_cap_usd: Decimal = Field(
        default=Decimal("0"), validation_alias="LLM_MONTHLY_CAP_USD", ge=0, le=20
    )
    llm_paid_minimum_remaining_usd: Decimal = Field(
        default=Decimal("1.00"),
        validation_alias="LLM_PAID_MINIMUM_REMAINING_USD",
        gt=0,
    )
    llm_request_timeout_seconds: float = Field(
        default=20, validation_alias="LLM_REQUEST_TIMEOUT_SECONDS", gt=0, le=120
    )
    llm_max_retries: int = Field(default=2, validation_alias="LLM_MAX_RETRIES", ge=0, le=3)
    llm_retry_base_delay_seconds: float = Field(
        default=0.25, validation_alias="LLM_RETRY_BASE_DELAY_SECONDS", ge=0, le=2
    )
    llm_retry_max_delay_seconds: float = Field(
        default=2, validation_alias="LLM_RETRY_MAX_DELAY_SECONDS", ge=0, le=8
    )

    @field_validator(
        "llm_primary_model",
        "llm_fallback_model",
        "llm_openai_pricing_model",
    )
    @classmethod
    def validate_model_identifier(cls, value: str | None) -> str | None:
        if value is not None and (not value.strip() or len(value) > 200):
            raise ValueError("LLM model identifiers must be non-empty and at most 200 characters")
        if value is None:
            return None
        normalized = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9._:/-]+", normalized):
            raise ValueError("LLM model identifiers contain unsupported characters")
        return normalized

    @model_validator(mode="after")
    def validate_llm_configuration(self) -> "Settings":
        pairs = (
            (self.llm_primary_provider, self.llm_primary_model, self.llm_primary_model_cost),
            (self.llm_fallback_provider, self.llm_fallback_model, self.llm_fallback_model_cost),
        )
        for provider, model, cost in pairs:
            if (provider is None) != (model is None):
                raise ValueError("Each configured LLM provider requires its model identifier")
            if model is not None and cost is None:
                raise ValueError("Each configured LLM model requires a free/paid cost classification")
            if model is None and cost is not None:
                raise ValueError("LLM cost classification requires a configured model")
            if provider == "openai" and model != self.llm_openai_pricing_model:
                raise ValueError(
                    "LLM_OPENAI_PRICING_MODEL must match each configured OpenAI model"
                )
        if self.llm_fallback_model is not None and self.llm_primary_model is None:
            raise ValueError("LLM fallback requires a configured primary model")
        if self.llm_paid_enabled and self.llm_monthly_cap_usd <= 0:
            raise ValueError("Paid LLM usage requires a positive monthly cap of at most USD 20")
        if (
            self.llm_monthly_cap_usd > 0
            and self.llm_paid_minimum_remaining_usd > self.llm_monthly_cap_usd
        ):
            raise ValueError(
                "LLM_PAID_MINIMUM_REMAINING_USD cannot exceed LLM_MONTHLY_CAP_USD"
            )
        if self.llm_retry_max_delay_seconds < self.llm_retry_base_delay_seconds:
            raise ValueError("LLM retry maximum delay must be at least the base delay")
        return self

    @field_validator("api_v1_prefix")
    @classmethod
    def validate_api_prefix(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("API_V1_PREFIX must start with '/'")
        if value == "/":
            raise ValueError("API_V1_PREFIX must include a path segment")
        return value.rstrip("/")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            origins = [origin.strip() for origin in value.split(",") if origin.strip()]
            if "*" in origins or "null" in origins:
                raise ValueError("CORS_ORIGINS must contain explicit origins")
            return origins
        return value

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, value: list[str]) -> list[str]:
        if "*" in value or "null" in value:
            raise ValueError("CORS_ORIGINS must contain explicit origins")
        if not value:
            raise ValueError("CORS_ORIGINS must contain at least one origin")
        normalized: list[str] = []
        for origin in value:
            origin = origin.strip()
            if not origin:
                raise ValueError("CORS_ORIGINS cannot contain blank origins")
            parsed = urlparse(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.username
                or parsed.password
                or parsed.path not in {"", "/"}
                or parsed.params
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("CORS_ORIGINS must contain absolute HTTP(S) origins")
            normalized.append(origin.rstrip("/"))
        return normalized
