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
    scryfall_user_agent: str = "Scry-X-AI/0.1 (local development)"
    database_path: str = str(BACKEND_DIR / "data" / "rules.db")
    frontend_origin: str = "http://localhost:5173"
    source_url: str = "https://media.wizards.com/2026/downloads/MagicCompRules%2020261106.txt"

    def validate_required(self) -> None:
        if self.llm_provider not in {"mock", "openai-compatible"}:
            raise RuntimeError("LLM_PROVIDER must be 'mock' or 'openai-compatible'")
        if self.llm_provider == "openai-compatible":
            if not self.llm_api_key:
                raise RuntimeError("LLM_API_KEY is required for openai-compatible provider")
            if not self.llm_model or self.llm_model == "mock":
                raise RuntimeError("LLM_MODEL is required for openai-compatible provider")


@lru_cache
def get_settings() -> Settings:
    return Settings()
