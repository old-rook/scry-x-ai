import os
from functools import lru_cache


class Settings:
    def __init__(self) -> None:
        self.llm_provider = os.getenv("LLM_PROVIDER", "mock")
        self.llm_api_key = os.getenv("LLM_API_KEY")
        self.llm_model = os.getenv("LLM_MODEL", "mock")
        self.scryfall_user_agent = os.getenv(
            "SCRYFALL_USER_AGENT", "Scry-X-AI/0.1 (local development)"
        )
        self.database_path = os.getenv(
            "DATABASE_PATH",
            os.path.join(os.path.dirname(__file__), "..", "..", "data", "rules.db"),
        )
        self.frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
        self.source_url = os.getenv(
            "RULES_SOURCE_URL",
            "https://media.wizards.com/2026/downloads/MagicCompRules 2026.txt",
        )

    def validate_required(self) -> None:
        if self.llm_provider != "mock" and not self.llm_api_key:
            raise RuntimeError("LLM_API_KEY is required for non-mock providers")


@lru_cache
def get_settings() -> Settings:
    return Settings()
