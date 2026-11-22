import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.main import app, create_app
from app.providers.scryfall import ScryfallProvider
from app.schemas.answers import (
    AnswerRequest,
    AnswerResponse,
    AnswerSource,
    ComprehensiveRuleSource,
    ConversationTurn,
)
from app.schemas.auth import AuthResponse, LoginRequest, LogoutResponse, RegisterRequest
from app.schemas.cards import CardDetail, CardSearchRequest, CardSearchResponse
from app.schemas.conversations import (
    ConversationCreateRequest,
    ConversationDetail,
    ConversationListResponse,
)
from app.rules.service import RulesService


client = TestClient(app)


def make_health_dependencies(tmp_path: Path, *, scryfall_status: int = 200):
    provider = ScryfallProvider(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                scryfall_status,
                json={
                    "object": "catalog",
                    "data": ["Creature"],
                    "total_values": 1,
                } if scryfall_status == 200 else {},
                request=request,
            )
        )
    )
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    verified_at = datetime.now(timezone.utc)
    timestamp = verified_at.isoformat()
    (rules_dir / "active.json").write_text(
        json.dumps(
            {
                "format_version": 1,
                "status": "verified",
                "active": {
                    "version": "20261106",
                    "publication_date": "2026-11-06",
                    "verified_at": timestamp,
                    "checksum": "private-checksum",
                    "source_url": "https://private.example/rules.txt",
                    "rules_file": "rules.json",
                    "source_file": "rules.txt",
                    "rule_count": 1182,
                },
                "latest_known_official": {
                    "version": "20261106",
                    "publication_date": "2026-11-06",
                    "source_url": "https://private.example/rules.txt",
                    "discovered_at": timestamp,
                },
                "last_verified_at": timestamp,
            }
        ),
        encoding="utf-8",
    )
    rules_service = RulesService(
        rules_dir,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(503, request=request)
        ),
    )
    return provider, rules_service


def test_health_endpoint(tmp_path: Path) -> None:
    provider, rules_service = make_health_dependencies(tmp_path)
    with TestClient(
        create_app(
            Settings(_env_file=None, database_url=None, rules_refresh_mode="external"),
            card_provider=provider,
            rules_service=rules_service,
        )
    ) as test_client:
        response = test_client.get("/api/v1/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == {"status": "not_configured"}
    assert data["scryfall"] == {"status": "ok"}
    assert data["rules"]["status"] == "ok"
    assert data["rules"]["latest_known_official"]["version"] == "20261106"
    assert data["rules"]["latest_known_official"]["publication_date"] == "2026-11-06"
    assert data["rules"]["latest_verified_local"]["version"] == "20261106"
    assert data["rules"]["latest_verified_local"]["publication_date"] == "2026-11-06"
    assert data["rules"]["refresh_in_progress"] is False
    assert data["ai"] == {"status": "not_configured", "providers": []}
    assert "source_url" not in response.text
    assert "private-checksum" not in response.text


def test_application_uses_api_prefix_and_cors_settings(tmp_path: Path) -> None:
    settings = Settings(
        api_v1_prefix="/api/test",
        cors_origins=["https://example.test"],
    )
    provider, rules_service = make_health_dependencies(tmp_path)
    configured_app = create_app(settings, card_provider=provider, rules_service=rules_service)
    with TestClient(configured_app) as client:
        response = client.get(
            "/api/test/health",
            headers={"Origin": "https://example.test"},
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://example.test"


def test_health_degrades_for_unavailable_scryfall(tmp_path: Path) -> None:
    provider, rules_service = make_health_dependencies(tmp_path, scryfall_status=503)
    with TestClient(
        create_app(
            Settings(rules_refresh_mode="external"),
            card_provider=provider,
            rules_service=rules_service,
        )
    ) as test_client:
        response = test_client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["scryfall"] == {"status": "unavailable"}


def test_health_marks_rules_stale_when_official_version_differs(tmp_path: Path) -> None:
    provider, rules_service = make_health_dependencies(tmp_path)
    state_path = tmp_path / "rules" / "active.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["latest_known_official"]["version"] = "20261201"
    state_path.write_text(json.dumps(state), encoding="utf-8")

    with TestClient(
        create_app(
            Settings(rules_refresh_mode="external"),
            card_provider=provider,
            rules_service=rules_service,
        )
    ) as test_client:
        response = test_client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["rules"]["status"] == "stale"
    assert response.json()["rules"]["latest_known_official"]["version"] == "20261201"
    assert response.json()["rules"]["latest_verified_local"]["version"] == "20261106"


def test_health_marks_rules_stale_after_verification_expires(
    tmp_path: Path,
    monkeypatch,
) -> None:
    provider, rules_service = make_health_dependencies(tmp_path)
    state_path = tmp_path / "rules" / "active.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    expired_at = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    state["active"]["verified_at"] = expired_at
    state["last_verified_at"] = expired_at
    state_path.write_text(json.dumps(state), encoding="utf-8")

    async def skip_startup_refresh(mode: str, interval_hours: int) -> None:
        return None

    monkeypatch.setattr(rules_service, "start_background_refresh", skip_startup_refresh)
    with TestClient(
        create_app(
            Settings(rules_refresh_mode="external"),
            card_provider=provider,
            rules_service=rules_service,
        )
    ) as test_client:
        response = test_client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["rules"]["status"] == "stale"
    reported_at = response.json()["rules"]["latest_verified_local"]["verified_at"]
    assert datetime.fromisoformat(reported_at.replace("Z", "+00:00")) == datetime.fromisoformat(
        expired_at
    )


@pytest.mark.parametrize(
    "active",
    [
        "invalid",
        {"verified_at": "2026-11-22T09:00:00+00:00"},
        {"version": "20261106"},
        {"version": " ", "verified_at": "2026-11-22T09:00:00+00:00"},
        {"version": "20261106", "verified_at": "invalid"},
    ],
)
def test_health_fails_closed_for_malformed_active_rules_manifest(
    tmp_path: Path,
    active: object,
) -> None:
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    verified_at = datetime.now(timezone.utc).isoformat()
    (rules_dir / "active.json").write_text(
        json.dumps(
            {
                "format_version": 1,
                "status": "verified",
                "active": active,
                "latest_known_official": {"version": "20261106"},
                "last_verified_at": verified_at,
            }
        ),
        encoding="utf-8",
    )
    rules_service = RulesService(rules_dir)
    try:
        summary = rules_service.health_summary()
        assert summary["status"] == "unavailable"
        assert summary["latest_verified_local"] is None
    finally:
        asyncio.run(rules_service.close())


def test_health_reports_provider_unavailable_without_secret(tmp_path: Path) -> None:
    provider, rules_service = make_health_dependencies(tmp_path)
    settings = Settings(
        rules_refresh_mode="external",
        llm_primary_provider="openrouter",
        llm_primary_model="health-test-model",
        llm_primary_model_cost="free",
    )
    with TestClient(
        create_app(
            settings,
            card_provider=provider,
            rules_service=rules_service,
        )
    ) as test_client:
        response = test_client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["ai"] == {
        "status": "unavailable",
        "providers": [
            {
                "provider": "openrouter",
                "model": "health-test-model",
                "availability": "unavailable",
            }
        ],
    }


def test_health_degrades_when_one_configured_ai_provider_is_unavailable(
    tmp_path: Path,
) -> None:
    provider, rules_service = make_health_dependencies(tmp_path)
    settings = Settings(
        rules_refresh_mode="external",
        llm_primary_provider="openrouter",
        llm_primary_model="primary-model",
        llm_primary_model_cost="free",
        llm_fallback_provider="gemini",
        llm_fallback_model="fallback-model",
        llm_fallback_model_cost="free",
        llm_gemini_api_key="not-exposed",
    )
    with TestClient(
        create_app(
            settings,
            card_provider=provider,
            rules_service=rules_service,
        )
    ) as test_client:
        response = test_client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["ai"] == {
        "status": "degraded",
        "providers": [
            {
                "provider": "openrouter",
                "model": "primary-model",
                "availability": "unavailable",
            },
            {
                "provider": "gemini",
                "model": "fallback-model",
                "availability": "configured",
            },
        ],
    }
    assert "not-exposed" not in response.text


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
        "RulesStatus": app.openapi()["components"]["schemas"]["RulesStatus"],
        "RulesVersionSummary": app.openapi()["components"]["schemas"]["RulesVersionSummary"],
        "AIStatus": app.openapi()["components"]["schemas"]["AIStatus"],
        "AIProviderStatus": app.openapi()["components"]["schemas"]["AIProviderStatus"],
        "CardDetail": CardDetail.model_json_schema(),
        "CardSearchRequest": CardSearchRequest.model_json_schema(),
        "CardSearchResponse": CardSearchResponse.model_json_schema(),
        "AnswerRequest": AnswerRequest.model_json_schema(),
        "AnswerResponse": AnswerResponse.model_json_schema(),
        "AnswerSource": AnswerSource.model_json_schema(),
        "ComprehensiveRuleSource": ComprehensiveRuleSource.model_json_schema(),
        "ConversationTurn": ConversationTurn.model_json_schema(),
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
