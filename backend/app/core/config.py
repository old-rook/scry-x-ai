from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]
REPOSITORY_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(REPOSITORY_DIR / ".env"), str(BACKEND_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_provider: str = "mock"
    llm_api_key: str | None = None
    llm_model: str = "mock"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_fallback_models: str = "gemini-4-neon,gemini-3.6-flash"
    prefer_builtin_answers: bool = True
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_fallback_models: str = ""
    scryfall_user_agent: str = "Scry-X-AI/0.1 (local development)"
    database_path: str = str(BACKEND_DIR / "data" / "rules.db")
    frontend_origin: str = "http://localhost:5173"
    source_url: str = "https://media.wizards.com/2026/downloads/MagicCompRules%2020261106.txt"

    @property
    def fallback_model_ids(self) -> list[str]:
        return self._parse_model_ids(self.llm_fallback_models, self.llm_model)

    @property
    def openrouter_fallback_model_ids(self) -> list[str]:
        return self._parse_model_ids(self.openrouter_fallback_models)

    @staticmethod
    def _parse_model_ids(value: str, exclude: str | None = None) -> list[str]:
        models = []
        for model in value.split(","):
            normalized = model.strip()
            if normalized and normalized != exclude and normalized not in models:
                models.append(normalized)
        return models

    def validate_required(self) -> None:
        if self.llm_provider not in {"mock", "openai-compatible"}:
            raise RuntimeError("LLM_PROVIDER must be 'mock' or 'openai-compatible'")
        if self.llm_provider == "openai-compatible":
            if not self.llm_api_key:
                raise RuntimeError("LLM_API_KEY is required for openai-compatible provider")
            if not self.llm_model or self.llm_model == "mock":
                raise RuntimeError("LLM_MODEL is required for openai-compatible provider")
            if len(self.fallback_model_ids) < 2:
                raise RuntimeError(
                    "LLM_FALLBACK_MODELS must contain at least two distinct fallback model IDs"
                )
            if self.openrouter_fallback_model_ids and not self.openrouter_api_key:
                raise RuntimeError(
                    "OPENROUTER_API_KEY is required when OPENROUTER_FALLBACK_MODELS is configured"
                )


@lru_cache
def get_settings() -> Settings:
    return Settings()
