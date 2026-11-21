from .rules_repository import RulesRepository
from ..api.schemas import ModelAnswer


def validate_answer(answer: dict, context: dict) -> ModelAnswer:
    parsed = ModelAnswer.model_validate(answer)
    evidence = {item["evidence_id"] for item in context["rules"]}
    evidence.update(item["evidence_id"] for item in context["rulings"])
    evidence.update(f"card-{item['oracle_id']}" for item in context["cards"])
    for citation in parsed.citations:
        if citation.evidence_id not in evidence:
            raise ValueError("Model cited evidence that was not retrieved")
    return parsed
