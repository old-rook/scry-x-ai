import json
from pathlib import Path
import httpx
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.main import app, create_app
from app.providers.scryfall import ScryfallProvider
from app.schemas.answers import AnswerRequest, AnswerResponse, ComprehensiveRuleSource
from app.schemas.auth import AuthResponse, LoginRequest, LogoutResponse, RegisterRequest
from app.schemas.cards import CardDetail, CardSearchRequest, CardSearchResponse
from app.schemas.conversations import (
    ConversationCreateRequest,
    ConversationDetail,
    ConversationListResponse,
)
from app.rules.service import RulesService


client = TestClient(app)


def test_health_endpoint(tmp_path: Path) -> None:
    provider = ScryfallProvider(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"object": "catalog"})
        )
    )
    rules_service = RulesService(
        tmp_path / "rules",
        transport=httpx.MockTransport(lambda request: httpx.Response(503, request=request)),
    )
    with TestClient(
        create_app(
            Settings(database_url=None, rules_refresh_mode="external"),
            card_provider=provider,
            rules_service=rules_service,
        )
    ) as test_client:
        response = test_client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": {"status": "not_configured"},
        "scryfall": {"status": "ok"},
        "rules": {"status": "not_configured"},
        "ai": {"status": "not_configured", "providers": []},
    }


def test_application_uses_api_prefix_and_cors_settings() -> None:
    settings = Settings(
        api_v1_prefix="/api/test",
        cors_origins=["https://example.test"],
    )
    configured_app = create_app(settings)
    client = TestClient(configured_app)

    response = client.get(
        "/api/test/health",
        headers={"Origin": "https://example.test"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://example.test"


def test_openapi_documents_health_contract() -> None:
    schema = app.openapi()

    assert "/api/v1/health" in schema["paths"]
    assert "HealthResponse" in schema["components"]["schemas"]


def test_answer_request_rejects_empty_question() -> None:
    try:
        AnswerRequest(question=" ")
    except ValidationError:
        return

    raise AssertionError("AnswerRequest accepted an empty question")


def test_card_search_rejects_invalid_limit() -> None:
    try:
        CardSearchRequest(q="Lightning Bolt", limit=101)
    except ValidationError:
        return

    raise AssertionError("CardSearchRequest accepted a limit above 100")


def test_conversation_title_is_bounded() -> None:
    try:
        ConversationCreateRequest(title="")
    except ValidationError:
        return

    raise AssertionError("ConversationCreateRequest accepted an empty title")


def test_answer_request_rejects_unknown_fields() -> None:
    try:
        AnswerRequest(question="Test", unexpected=True)
    except ValidationError:
        return

    raise AssertionError("AnswerRequest accepted an unknown field")


def test_root_api_prefix_is_rejected() -> None:
    try:
        Settings(api_v1_prefix="/")
    except ValidationError:
        return

    raise AssertionError("Settings accepted '/' as an API prefix")


def test_wildcard_cors_origin_is_rejected_for_list_config() -> None:
    try:
        Settings(cors_origins=["*"])
    except ValidationError:
        return

    raise AssertionError("Settings accepted a wildcard CORS origin")


def test_cors_origins_parse_comma_separated_environment(monkeypatch) -> None:
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "http://localhost:3000,https://example.test",
    )

    settings = Settings()

    assert settings.cors_origins == [
        "http://localhost:3000",
        "https://example.test",
    ]


def test_access_token_lifetime_parses_environment(monkeypatch) -> None:
    monkeypatch.setenv("ACCESS_TOKEN_LIFETIME_MINUTES", "15")

    assert Settings().access_token_lifetime_minutes == 15


def test_frontend_contract_fixture_matches_openapi() -> None:
    contract_path = Path(__file__).resolve().parents[2] / "frontend" / "lib" / "api-contract.json"
    contracts = json.loads(contract_path.read_text(encoding="utf-8"))
    model_types = {
        "HealthResponse": app.openapi()["components"]["schemas"]["HealthResponse"],
        "DependencyStatus": app.openapi()["components"]["schemas"]["DependencyStatus"],
        "AIStatus": app.openapi()["components"]["schemas"]["AIStatus"],
        "AIProviderStatus": app.openapi()["components"]["schemas"]["AIProviderStatus"],
        "CardDetail": CardDetail.model_json_schema(),
        "CardSearchRequest": CardSearchRequest.model_json_schema(),
        "CardSearchResponse": CardSearchResponse.model_json_schema(),
        "AnswerRequest": AnswerRequest.model_json_schema(),
        "AnswerResponse": AnswerResponse.model_json_schema(),
        "ComprehensiveRuleSource": ComprehensiveRuleSource.model_json_schema(),
        "ConversationCreateRequest": ConversationCreateRequest.model_json_schema(),
        "ConversationDetail": ConversationDetail.model_json_schema(),
        "ConversationListResponse": ConversationListResponse.model_json_schema(),
        "RegisterRequest": RegisterRequest.model_json_schema(),
        "LoginRequest": LoginRequest.model_json_schema(),
        "AuthResponse": AuthResponse.model_json_schema(),
        "LogoutResponse": LogoutResponse.model_json_schema(),
    }

    for contract_name, contract in contracts.items():
        model_schema = model_types[contract_name]
        openapi_fields = set(model_schema.get("properties", {}))
        fixture_fields = set(contract["fields"])

        assert fixture_fields == openapi_fields, (
            f"{contract_name} contract fields differ: "
            f"frontend fixture={sorted(fixture_fields)}, "
            f"OpenAPI={sorted(openapi_fields)}"
        )
