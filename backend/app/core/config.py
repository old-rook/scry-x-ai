from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator
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
    access_token_lifetime_minutes: Literal[15] = 15
    app_environment: Literal["development", "test", "staging", "production"] = Field(
        default="development",
        validation_alias="APP_ENV",
    )
    api_v1_prefix: str = "/api/v1"
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

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
