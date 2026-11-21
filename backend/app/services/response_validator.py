from .rules_repository import RulesRepository
from ..api.schemas import ModelAnswer


def validate_answer(answer: dict, context: dict) -> ModelAnswer:
    parsed = ModelAnswer.model_validate(answer)
    evidence = {item["evidence_id"]: "comprehensive_rule" for item in context["rules"]}
    evidence.update({item["evidence_id"]: "card_ruling" for item in context["rulings"]})
    evidence.update({item["evidence_id"]: "card_text" for item in context["cards"]})
    for citation in parsed.citations:
        if evidence.get(citation.evidence_id) != citation.kind:
            raise ValueError("Model cited evidence that was not retrieved")
    return parsed
