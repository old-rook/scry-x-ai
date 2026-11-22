from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app, create_app


client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": {"status": "not_configured"},
        "scryfall": {"status": "not_configured"},
        "rules": {"status": "not_configured"},
        "ai": {"status": "not_configured"},
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
