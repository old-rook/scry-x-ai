from app.api.schemas import ModelAnswer
from app.services.response_validator import validate_answer


def test_validator_accepts_retrieved_evidence():
    answer = validate_answer({
        "status": "answered",
        "summary": "Supported.",
        "citations": [{"evidence_id": "rule-305-7", "kind": "comprehensive_rule", "reason": "Relevant"}],
    }, {
        "rules": [{"evidence_id": "rule-305-7"}],
        "rulings": [],
        "cards": [],
    })
    assert answer.status == "answered"


def test_validator_rejects_unknown_evidence():
    try:
        validate_answer({
            "status": "answered",
            "summary": "Unsupported.",
            "citations": [{"evidence_id": "rule-999", "kind": "comprehensive_rule"}],
        }, {"rules": [], "rulings": [], "cards": []})
    except ValueError:
        return
    raise AssertionError("Unknown citation was accepted")
