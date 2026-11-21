from fastapi.testclient import TestClient
from app import main
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


def test_judge_answers_deathtouch_and_trample():
    response = client.post("/api/v1/judge/ask", json={
        "question": "How does Deathtouch with Trample work?",
    })
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "answered"
    assert "1 damage" in body["summary"]
    assert {citation["label"] for citation in body["citations"]} == {
        "Comprehensive Rules 702.2c",
        "Comprehensive Rules 702.19a",
        "Comprehensive Rules 702.19b",
    }


def test_judge_answers_standalone_keywords():
    for keyword, explanation_text in (
        ("Trample", "attacking creature"),
        ("Double Strike", "second combat damage step"),
    ):
        response = client.post("/api/v1/judge/ask", json={"question": f"How does {keyword} work?"})
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "answered"
        assert explanation_text in " ".join(body["explanation"])
        assert body["citations"]


def test_judge_answers_blood_moon_and_urzas_saga(monkeypatch):
    async def no_cards(_question):
        return {"status": "resolved", "cards": [], "ambiguous": []}

    monkeypatch.setattr(main.card_lookup, "identify", no_cards)
    response = client.post("/api/v1/judge/ask", json={
        "question": "How Blood Moon and Urza's Saga interact?",
    })
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "answered"
    assert any("chapter abilities" in step for step in body["explanation"])
    assert any(citation["label"] == "Comprehensive Rules 305.7" for citation in body["citations"])
