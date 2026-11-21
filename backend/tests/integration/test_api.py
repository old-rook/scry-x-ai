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


def test_judge_answers_a_general_keyword_question_without_a_card():
    response = client.post("/api/v1/judge/ask", json={"question": "What is deathtouch?"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "answered"
    assert body["cards"] == []
    assert "deathtouch" in body["summary"].casefold()
    assert {citation["label"] for citation in body["citations"]} == {
        "Comprehensive Rules 702.2b",
        "Comprehensive Rules 702.2c",
    }


def test_judge_explains_a_trample_combat_scenario_without_card_names():
    response = client.post("/api/v1/judge/ask", json={
        "question": "WHat happens if my 2/2 with trample gets blocked by a 1/1 creature?"
    })

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "answered"
    assert body["cards"] == []
    assert "1 damage to the 1/1 blocker" in body["summary"]
    assert "remaining 1 damage to the defending player" in body["summary"]
    assert any("2/2 attacker, which survives" in step for step in body["explanation"])
    assert any(citation["label"] == "Comprehensive Rules 702.19b" for citation in body["citations"])


def test_judge_answers_deathtouch_trample_combat_without_relying_on_llm(monkeypatch):
    async def invalid_llm_answer(**_kwargs):
        return {
            "status": "answered",
            "summary": "Unsupported response",
            "explanation": [],
            "assumptions": [],
            "citations": [{"evidence_id": "missing", "kind": "comprehensive_rule", "reason": "Invalid"}],
            "uncertainties": [],
            "clarifying_question": None,
        }

    monkeypatch.setattr(main.llm, "generate_judge_answer", invalid_llm_answer)
    response = client.post("/api/v1/judge/ask", json={
        "question": "What happens when my 3/2 creature with deathtouch and trample gets blocked by a 1/1 creature?"
    })

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "answered"
    assert "1 damage to the 1/1 blocker" in body["summary"]
    assert "remaining 2 damage to the defending player" in body["summary"]
    assert any("3/2 attacker, which survives" in step for step in body["explanation"])
    assert {citation["label"] for citation in body["citations"]} == {
        "Comprehensive Rules 702.2c",
        "Comprehensive Rules 702.19a",
        "Comprehensive Rules 702.19b",
    }


def test_can_send_supported_question_to_llm_for_model_evaluation(monkeypatch):
    question = "What happens when my 3/2 creature with deathtouch and trample gets blocked by a 1/1 creature?"
    calls = []

    async def llm_answer(*, question, context):
        calls.append(question)
        rule = context["rules"][0]
        return {
            "status": "answered",
            "summary": "LLM evaluation response",
            "explanation": ["Generated from the retrieved rules."],
            "assumptions": [],
            "citations": [{
                "evidence_id": rule["evidence_id"],
                "kind": "comprehensive_rule",
                "reason": "Supports this evaluation response.",
            }],
            "uncertainties": [],
            "clarifying_question": None,
        }

    monkeypatch.setattr(main.settings, "prefer_builtin_answers", False)
    monkeypatch.setattr(main.llm, "generate_judge_answer", llm_answer)
    response = client.post("/api/v1/judge/ask", json={"question": question})

    assert response.status_code == 200
    assert response.json()["summary"] == "LLM evaluation response"
    assert calls == [question]


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
