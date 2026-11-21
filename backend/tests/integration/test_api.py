from fastapi.testclient import TestClient
from app.main import app


client = TestClient(app)


def test_health():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_rules_version():
    response = client.get("/api/v1/rules/version")
    assert response.status_code == 200
    assert response.json()["version_id"]


def test_identify_unknown_question():
    response = client.post("/api/v1/cards/identify", json={"question": "What happens during my turn?"})
    assert response.status_code == 200
    assert response.json()["status"] == "resolved"


def test_judge_with_confirmed_card():
    response = client.post("/api/v1/judge/ask", json={
        "question": "What happens to Blood Moon on the battlefield?",
        "confirmed_cards": [{"scryfall_id": "test-id"}],
    })
    assert response.status_code == 200
    assert response.json()["status"] in ("answered", "insufficient_evidence")
